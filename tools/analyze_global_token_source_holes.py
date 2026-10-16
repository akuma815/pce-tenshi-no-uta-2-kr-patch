#!/usr/bin/env python3
"""Audit source-hole capacity after applying one fixed global 25-glyph token table."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_context_source_holes import allocate, merge, split_banks, subtract  # noqa: E402
from patch_iso import encode_string  # noqa: E402

BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "global_token_source_hole_capacity.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
BANK = 8192
REDIRECT = 5
TOKEN_BYTES = list(range(0x03, 0x0B)) + list(range(0x0F, 0x20))


def choose_dictionary(context_strings):
	counts = Counter()
	# Weight a glyph once per unique string in every context where that string is needed.
	for strings in context_strings:
		for data in strings:
			for i in range(len(data) - 1):
				if 0xEB <= data[i] <= 0xEF:
					counts[data[i:i + 2]] += 1
	chosen = counts.most_common(len(TOKEN_BYTES))
	if len(chosen) != len(TOKEN_BYTES):
		raise ValueError("not enough global token candidates")
	return {token: sequence for token, (sequence, _) in zip(TOKEN_BYTES, chosen)}


def compress(data, dictionary):
	reverse = {sequence: token for token, sequence in dictionary.items()}
	out = bytearray()
	i = 0
	while i < len(data):
		token = reverse.get(data[i:i + 2])
		if token is None:
			out.append(data[i])
			i += 1
		else:
			out.append(token)
			i += 2
	return bytes(out)


def decompress(data, dictionary):
	out = bytearray()
	for value in data:
		out.extend(dictionary.get(value, bytes((value,))))
	return bytes(out)


def main():
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET)
		iso = source.read(9328 * SECTOR)
	rows = []
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			text = row["번역"].strip()
			if text:
				rows.append((int(row["키(ISO오프셋)"], 16),
				             encode_string(text, char_map) + b"\x00"))

	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	prepared = []
	seen = set()
	for owner, entries in (("primary", primary["logical_entries"]),
	                       ("overlay", overlay["entries"])):
		for entry in entries:
			if entry.get("physical_grid") is None:
				continue
			key = owner, entry["lba"], entry["load_sectors"]
			if key in seen:
				continue
			seen.add(key)
			base = entry["lba"] * SECTOR
			end = base + entry["load_sectors"] * SECTOR
			matched = [(offset, data) for offset, data in rows if base <= offset < end]
			if not matched:
				continue
			body_ranges, valid_rows = [], []
			for offset, data in matched:
				nul = iso.find(b"\x00", offset, min(end, ((offset // SECTOR) + 1) * SECTOR))
				if nul < 0 or nul + 1 - offset < REDIRECT:
					continue
				body_ranges.append((offset + REDIRECT, nul + 1))
				valid_rows.append((offset, data))
			free = split_banks(subtract(merge(body_ranges), []), base)
			prepared.append((owner, entry, matched, valid_rows, free, base))

	dictionary = choose_dictionary([{data for _, data in item[3]} for item in prepared])
	contexts = []
	for owner, entry, matched, valid_rows, free, base in prepared:
		originals = {data for _, data in valid_rows}
		compressed = {data: compress(data, dictionary) for data in originals}
		for original, packed in compressed.items():
			if decompress(packed, dictionary) != original:
				raise AssertionError("global token round-trip failed")
		chunks = set(compressed.values())
		placed, missing, remaining = allocate(free, chunks)
		used_banks = (entry["load_sectors"] + 3) // 4
		free_bank_start = base + used_banks * BANK
		window_end = base + 24 * BANK
		free_banks = [] if free_bank_start >= window_end else [[free_bank_start, window_end]]
		combined_placed, combined_missing, combined_remaining = allocate(free + free_banks, chunks)
		contexts.append({
			"owner": owner, "physical_grid": entry["physical_grid"],
			"lba": entry["lba"], "load_sectors": entry["load_sectors"],
			"translated_rows": len(matched), "redirectable_rows": len(valid_rows),
			"unique_strings": len(originals),
			"uncompressed_unique_bytes": sum(map(len, originals)),
			"compressed_unique_bytes": sum(map(len, chunks)),
			"token_savings_bytes": sum(map(len, originals)) - sum(map(len, chunks)),
			"source_hole_bytes": sum(b - a for a, b in free),
			"placed_unique_strings": placed, "missing_string_bytes": missing,
			"remaining_hole_bytes": remaining, "fits_source_holes": placed == len(chunks),
			"free_whole_bank_bytes": max(0, window_end - free_bank_start),
			"combined_placed_unique_strings": combined_placed,
			"combined_missing_string_bytes": combined_missing,
			"combined_remaining_bytes": combined_remaining,
			"fits_holes_plus_free_banks": combined_placed == len(chunks),
		})

	result = {
		"format": "GLOBAL-TOKEN-SOURCE-HOLE-CAPACITY",
		"scope": "Read-only per-context capacity audit with one fixed global dictionary.",
		"token_bytes": [f"{x:02x}" for x in TOKEN_BYTES],
		"token_dictionary": {f"{token:02x}": sequence.hex() for token, sequence in dictionary.items()},
		"dictionary_code_bytes": len(dictionary) * 2,
		"contexts": contexts,
		"context_count": len(contexts),
		"fits_contexts": sum(x["fits_source_holes"] for x in contexts),
		"failed_contexts": sum(not x["fits_source_holes"] for x in contexts),
		"total_missing_string_bytes": sum(x["missing_string_bytes"] for x in contexts),
		"combined_fits_contexts": sum(x["fits_holes_plus_free_banks"] for x in contexts),
		"combined_failed_contexts": sum(not x["fits_holes_plus_free_banks"] for x in contexts),
		"combined_missing_string_bytes": sum(x["combined_missing_string_bytes"] for x in contexts),
		"total_token_savings_bytes": sum(x["token_savings_bytes"] for x in contexts),
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("contexts:", result["context_count"])
	print("global token savings:", result["total_token_savings_bytes"])
	print("fits source holes:", result["fits_contexts"])
	print("failed:", result["failed_contexts"])
	print("missing string bytes:", result["total_missing_string_bytes"])
	print("fits holes + free banks:", result["combined_fits_contexts"])
	print("combined failed:", result["combined_failed_contexts"])
	print("combined missing bytes:", result["combined_missing_string_bytes"])
	print("output:", OUT)


if __name__ == "__main__":
	main()
