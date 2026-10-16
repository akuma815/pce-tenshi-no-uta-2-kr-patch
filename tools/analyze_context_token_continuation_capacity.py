#!/usr/bin/env python3
"""Audit per-context 25-glyph dictionaries plus continuation chains."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_context_source_holes import merge, split_banks  # noqa: E402
from analyze_global_token_source_holes import TOKEN_BYTES, compress, decompress  # noqa: E402
from analyze_global_token_continuation_capacity import allocate_all  # noqa: E402
from pack_fragmented_area_chains import take_whole  # noqa: E402
from patch_iso import encode_string  # noqa: E402

BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "context_token_continuation_capacity.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
BANK = 8192
REDIRECT = 5
DICTIONARY_BYTES = 50


def choose_context_dictionary(strings, fallback_sequences):
	counts = Counter()
	for data in strings:
		for i in range(len(data) - 1):
			if 0xEB <= data[i] <= 0xEF:
				counts[data[i:i + 2]] += 1
	sequences = [sequence for sequence, _ in counts.most_common(len(TOKEN_BYTES))]
	for sequence in fallback_sequences:
		if len(sequences) == len(TOKEN_BYTES):
			break
		if sequence not in sequences:
			sequences.append(sequence)
	if len(sequences) != len(TOKEN_BYTES):
		raise ValueError("not enough dictionary padding glyphs")
	return dict(zip(TOKEN_BYTES, sequences))


def main():
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	fallback_sequences = list(dict.fromkeys(bytes.fromhex(x) for x in char_map.values()))
	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET)
		iso = source.read(9328 * SECTOR)
	rows = []
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			text = row["번역"].strip()
			if text:
				rows.append((int(row["키(ISO오프셋)"], 16), encode_string(text, char_map) + b"\x00"))

	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	contexts, seen = [], set()
	for owner, entries in (("primary", primary["logical_entries"]), ("overlay", overlay["entries"])):
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
			body_ranges, valid = [], []
			for offset, data in matched:
				nul = iso.find(b"\x00", offset, min(end, ((offset // SECTOR) + 1) * SECTOR))
				if nul < 0 or nul + 1 - offset < REDIRECT:
					continue
				body_ranges.append([offset + REDIRECT, nul + 1])
				valid.append((offset, data))
			originals = {data for _, data in valid}
			if not originals:
				continue
			dictionary = choose_context_dictionary(originals, fallback_sequences)
			chunks = {compress(data, dictionary) for data in originals}
			assert all(decompress(compress(data, dictionary), dictionary) == data for data in originals)
			free = split_banks(merge(body_ranges), base)
			used_banks = (entry["load_sectors"] + 3) // 4
			free_bank_start = base + used_banks * BANK
			window_end = base + 24 * BANK
			if free_bank_start < window_end:
				free += split_banks([[free_bank_start, window_end]], base)
			initial_free = sum(b - a for a, b in free)
			dictionary_address = take_whole(free, DICTIONARY_BYTES)
			if dictionary_address is None:
				fits, placed, failed_bytes, markers, segments, remaining = False, 0, 0, 0, 0, initial_free
			else:
				fits, placed, failed_bytes, markers, segments, remaining = allocate_all(free, chunks)
			contexts.append({
				"owner": owner, "physical_grid": entry["physical_grid"], "lba": entry["lba"],
				"load_sectors": entry["load_sectors"], "unique_strings": len(chunks),
				"uncompressed_unique_bytes": sum(map(len, originals)),
				"compressed_unique_bytes": sum(map(len, chunks)),
				"token_savings_bytes": sum(map(len, originals)) - sum(map(len, chunks)),
				"available_bytes": initial_free, "dictionary_bytes": DICTIONARY_BYTES,
				"dictionary_area_offset": None if dictionary_address is None else dictionary_address - base,
				"token_dictionary": {f"{k:02x}": v.hex() for k, v in dictionary.items()},
				"fits_context_token_continuation": fits, "placed_strings": placed,
				"first_failed_string_bytes": failed_bytes, "continuation_markers": markers,
				"segments": segments, "remaining_bytes": remaining,
			})

	result = {
		"format": "CONTEXT-TOKEN-CONTINUATION-CAPACITY",
		"scope": "Read-only capacity audit; each 50-byte dictionary and all four-byte continuation records are charged.",
		"contexts": contexts, "context_count": len(contexts),
		"fits_contexts": sum(x["fits_context_token_continuation"] for x in contexts),
		"failed_contexts": sum(not x["fits_context_token_continuation"] for x in contexts),
		"continuation_markers": sum(x["continuation_markers"] for x in contexts),
		"dictionary_bytes_total": len(contexts) * DICTIONARY_BYTES,
		"token_savings_bytes": sum(x["token_savings_bytes"] for x in contexts),
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("contexts:", result["context_count"])
	print("fits context token + continuation:", result["fits_contexts"])
	print("failed:", result["failed_contexts"])
	print("token savings:", result["token_savings_bytes"])
	print("dictionary bytes:", result["dictionary_bytes_total"])
	print("continuation markers:", result["continuation_markers"])
	for x in contexts:
		if not x["fits_context_token_continuation"]:
			print("FAIL", x["owner"], x["physical_grid"], "placed", x["placed_strings"],
			      "/", x["unique_strings"], "remaining", x["remaining_bytes"])
	print("output:", OUT)


if __name__ == "__main__":
	main()
