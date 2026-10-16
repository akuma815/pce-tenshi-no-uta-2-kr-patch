#!/usr/bin/env python3
"""Build a read-only in-place translation plan capped to each original byte length."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from patch_iso import encode_string  # noqa: E402

ISO = ROOT / "extracted_bin" / "Track02_data.iso"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
OUT_JSON = ROOT / "translation" / "fixed_length_translation_plan.json"
OUT_TSV = ROOT / "translation" / "fixed_length_translation_review.tsv"
SECTOR = 2048


def units(text: str):
	"""Yield indivisible encoded units, keeping native markup/control sequences intact."""
	i = 0
	while i < len(text):
		if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in "np":
			yield text[i:i + 2]
			i += 2
		elif text[i] == "{" and "}" in text[i + 1:]:
			end = text.index("}", i + 1) + 1
			yield text[i:end]
			i = end
		elif text[i] == "#" and i + 1 < len(text):
			yield text[i:i + 2]
			i += 2
		elif text[i] == "%" and i + 1 < len(text):
			end = i + 2
			# Existing merged text commonly uses three-byte forms such as %f2.
			if end < len(text) and text[end].isalnum():
				end += 1
			yield text[i:end]
			i = end
		else:
			yield text[i]
			i += 1


def truncate_encoded(text: str, capacity: int, char_map):
	out = bytearray()
	kept = []
	all_units = list(units(text))
	for unit in all_units:
		data = encode_string(unit, char_map)
		if len(out) + len(data) > capacity:
			break
		out.extend(data)
		kept.append(unit)
	return "".join(kept), bytes(out), len(kept) < len(all_units), len(all_units) - len(kept)


def main():
	iso = ISO.read_bytes()
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	entries = []
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			translation = row["번역"].strip()
			if not translation:
				continue
			offset = int(row["키(ISO오프셋)"], 16)
			# Script streams may cross a sector boundary; cap pathological scans at 2 KiB.
			limit = min(len(iso), offset + SECTOR)
			nul = iso.find(b"\x00", offset, limit)
			if nul < 0:
				raise ValueError(f"unterminated source at {offset:07X}")
			capacity = nul - offset
			full = encode_string(translation, char_map)
			kept_text, kept, truncated, dropped_units = truncate_encoded(translation, capacity, char_map)
			assert len(kept) <= capacity
			assert encode_string(kept_text, char_map) == kept
			entries.append({
				"source_offset": offset, "region": row["영역"], "original": row["원문"],
				"translation": translation, "kept_translation": kept_text,
				"source_capacity_bytes": capacity, "full_translation_bytes": len(full),
				"kept_translation_bytes": len(kept), "truncated": truncated,
				"dropped_units": dropped_units, "replacement_hex": (kept + b"\x00").hex(),
			})

	result = {
		"format": "FIXED-LENGTH-TRANSLATION-PLAN",
		"policy": "Translation is truncated only at encoded unit boundaries and terminated by NUL; it never exceeds the original body length.",
		"entries": entries, "entry_count": len(entries),
		"fits_without_truncation": sum(not x["truncated"] for x in entries),
		"truncated_entries": sum(x["truncated"] for x in entries),
		"empty_after_truncation": sum(not x["kept_translation"] for x in entries),
		"maximum_dropped_units": max((x["dropped_units"] for x in entries), default=0),
	}
	OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	with OUT_TSV.open("w", encoding="utf-8-sig", newline="") as output:
		writer = csv.writer(output, delimiter="\t", lineterminator="\n")
		writer.writerow(["키(ISO오프셋)", "영역", "원문바이트", "번역바이트", "유지바이트", "잘림", "유지번역", "전체번역"])
		for x in entries:
			writer.writerow([f'{x["source_offset"]:07x}', x["region"], x["source_capacity_bytes"],
			                 x["full_translation_bytes"], x["kept_translation_bytes"],
			                 "Y" if x["truncated"] else "N", x["kept_translation"], x["translation"]])
	print("entries:", result["entry_count"])
	print("fits without truncation:", result["fits_without_truncation"])
	print("truncated:", result["truncated_entries"])
	print("empty after truncation:", result["empty_after_truncation"])
	print("output:", OUT_JSON)


if __name__ == "__main__":
	main()
