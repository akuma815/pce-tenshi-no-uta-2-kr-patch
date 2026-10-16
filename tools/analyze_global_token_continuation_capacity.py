#!/usr/bin/env python3
"""Audit fixed global glyph tokens plus bank-safe continuation chains."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_context_source_holes import merge, split_banks  # noqa: E402
from analyze_global_token_source_holes import choose_dictionary, compress, decompress  # noqa: E402
from pack_fragmented_area_chains import allocate_chain  # noqa: E402
from patch_iso import encode_string  # noqa: E402

BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "global_token_continuation_capacity.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
BANK = 8192
REDIRECT = 5
SCRATCH_BASE = -BANK
MAX_SCRATCH = BANK


def allocate_all(free, chunks):
	free = [x[:] for x in free]
	markers = segments = placed = 0
	for data in sorted(chunks, key=len, reverse=True):
		chain = allocate_chain(free, data)
		if chain is None:
			return False, placed, len(data), markers, segments, sum(b - a for a, b in free)
		placed += 1
		segments += len(chain)
		markers += len(chain) - 1
	return True, placed, 0, markers, segments, sum(b - a for a, b in free)


def minimum_scratch_bytes(free, chunks):
	"""Find the exact minimum single-bank scratch span for this deterministic allocator."""
	for size in range(MAX_SCRATCH + 1):
		candidate = [x[:] for x in free]
		if size:
			candidate.append([SCRATCH_BASE, SCRATCH_BASE + size])
		if allocate_all(candidate, chunks)[0]:
			return size
	return None


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
				rows.append((int(row["키(ISO오프셋)"], 16), encode_string(text, char_map) + b"\x00"))

	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	prepared, seen = [], set()
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
			prepared.append((owner, entry, base, body_ranges, valid))

	dictionary = choose_dictionary([{data for _, data in item[4]} for item in prepared])
	contexts = []
	for owner, entry, base, body_ranges, valid in prepared:
		originals = {data for _, data in valid}
		chunks = {compress(data, dictionary) for data in originals}
		assert all(decompress(compress(data, dictionary), dictionary) == data for data in originals)
		free = split_banks(merge(body_ranges), base)
		used_banks = (entry["load_sectors"] + 3) // 4
		free_bank_start = base + used_banks * BANK
		window_end = base + 24 * BANK
		if free_bank_start < window_end:
			free += split_banks([[free_bank_start, window_end]], base)
		fits, placed, failed_bytes, markers, segments, remaining = allocate_all(free, chunks)
		minimum_scratch = 0 if fits else minimum_scratch_bytes(free, chunks)
		contexts.append({
			"owner": owner, "physical_grid": entry["physical_grid"], "lba": entry["lba"],
			"load_sectors": entry["load_sectors"], "unique_strings": len(chunks),
			"compressed_unique_bytes": sum(map(len, chunks)),
			"available_bytes": sum(b - a for a, b in free),
			"fits_token_continuation": fits, "placed_strings": placed,
			"first_failed_string_bytes": failed_bytes, "continuation_markers": markers,
			"segments": segments, "remaining_bytes": remaining,
			"minimum_single_bank_scratch_bytes": minimum_scratch,
		})

	result = {
		"format": "GLOBAL-TOKEN-CONTINUATION-CAPACITY",
		"scope": "Read-only capacity audit; four-byte continuation records are included.",
		"token_dictionary": {f"{k:02x}": v.hex() for k, v in dictionary.items()},
		"contexts": contexts, "context_count": len(contexts),
		"fits_contexts": sum(x["fits_token_continuation"] for x in contexts),
		"failed_contexts": sum(not x["fits_token_continuation"] for x in contexts),
		"continuation_markers": sum(x["continuation_markers"] for x in contexts),
		"remaining_bytes": sum(x["remaining_bytes"] for x in contexts),
		"maximum_minimum_scratch_bytes": max(
			x["minimum_single_bank_scratch_bytes"] or 0 for x in contexts),
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("contexts:", result["context_count"])
	print("fits token + continuation:", result["fits_contexts"])
	print("failed:", result["failed_contexts"])
	print("continuation markers:", result["continuation_markers"])
	print("remaining bytes:", result["remaining_bytes"])
	print("maximum minimum scratch bytes:", result["maximum_minimum_scratch_bytes"])
	for x in contexts:
		if not x["fits_token_continuation"]:
			print("FAIL", x["owner"], x["physical_grid"], "placed", x["placed_strings"],
			      "/", x["unique_strings"], "remaining", x["remaining_bytes"],
			      "min_scratch", x["minimum_single_bank_scratch_bytes"])
	print("output:", OUT)


if __name__ == "__main__":
	main()
