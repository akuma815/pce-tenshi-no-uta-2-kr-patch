#!/usr/bin/env python3
"""Independent per-context feasibility audit using only reclaimed source-string bodies."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from patch_iso import encode_string  # noqa: E402

BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "context_source_hole_capacity.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
BANK = 8192
REDIRECT = 5


def merge(ranges):
	out = []
	for start, end in sorted(ranges):
		if start >= end:
			continue
		if out and start <= out[-1][1]:
			out[-1][1] = max(out[-1][1], end)
		else:
			out.append([start, end])
	return out


def subtract(ranges, reserved):
	result = ranges
	for cut_start, cut_end in merge(reserved):
		next_ranges = []
		for start, end in result:
			if cut_end <= start or cut_start >= end:
				next_ranges.append([start, end])
			else:
				if start < cut_start:
					next_ranges.append([start, cut_start])
				if cut_end < end:
					next_ranges.append([cut_end, end])
		result = next_ranges
	return result


def split_banks(ranges, base):
	out = []
	for start, end in ranges:
		while start < end:
			boundary = base + ((start - base) // BANK + 1) * BANK
			stop = min(end, boundary)
			out.append([start, stop])
			start = stop
	return out


def allocate(free, chunks):
	free = [x[:] for x in free]
	placed = 0
	missing = 0
	for data in sorted(chunks, key=len, reverse=True):
		candidates = [(end - start, i) for i, (start, end) in enumerate(free)
		              if end - start >= len(data)]
		if not candidates:
			missing += len(data)
			continue
		_, index = min(candidates)
		free[index][0] += len(data)
		if free[index][0] == free[index][1]:
			free.pop(index)
		placed += 1
	return placed, missing, sum(end - start for start, end in free)


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
	contexts = []
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
			body_ranges, redirects = [], []
			valid_rows = []
			for offset, data in matched:
				nul = iso.find(b"\x00", offset, min(end, ((offset // SECTOR) + 1) * SECTOR))
				if nul < 0 or nul + 1 - offset < REDIRECT:
					continue
				redirects.append((offset, offset + REDIRECT))
				body_ranges.append((offset + REDIRECT, nul + 1))
				valid_rows.append((offset, data))
			free = split_banks(subtract(merge(body_ranges), redirects), base)
			unique = {data for _, data in valid_rows}
			placed, missing, remaining = allocate(free, unique)
			used_banks = (entry["load_sectors"] + 3) // 4
			free_bank_start = base + used_banks * BANK
			window_end = base + 24 * BANK
			free_banks = [] if free_bank_start >= window_end else [[free_bank_start, window_end]]
			combined_placed, combined_missing, combined_remaining = allocate(
				free + free_banks, unique)
			contexts.append({
				"owner": owner, "physical_grid": entry["physical_grid"],
				"lba": entry["lba"], "load_sectors": entry["load_sectors"],
				"translated_rows": len(matched), "redirectable_rows": len(valid_rows),
				"unique_strings": len(unique), "source_hole_bytes": sum(b - a for a, b in free),
				"placed_unique_strings": placed, "missing_string_bytes": missing,
				"remaining_hole_bytes": remaining,
				"fits_source_holes": placed == len(unique),
				"free_whole_bank_bytes": max(0, window_end - free_bank_start),
				"combined_placed_unique_strings": combined_placed,
				"combined_missing_string_bytes": combined_missing,
				"combined_remaining_bytes": combined_remaining,
				"fits_holes_plus_free_banks": combined_placed == len(unique),
			})

	result = {
		"format": "CONTEXT-SOURCE-HOLE-CAPACITY",
		"scope": "Per-context independent lower bound; cross-context disk allocation not yet resolved.",
		"contexts": contexts,
		"context_count": len(contexts),
		"fits_contexts": sum(x["fits_source_holes"] for x in contexts),
		"failed_contexts": sum(not x["fits_source_holes"] for x in contexts),
		"total_missing_string_bytes": sum(x["missing_string_bytes"] for x in contexts),
		"combined_fits_contexts": sum(x["fits_holes_plus_free_banks"] for x in contexts),
		"combined_failed_contexts": sum(not x["fits_holes_plus_free_banks"] for x in contexts),
		"combined_missing_string_bytes": sum(x["combined_missing_string_bytes"] for x in contexts),
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("contexts:", result["context_count"])
	print("fits source holes:", result["fits_contexts"])
	print("failed:", result["failed_contexts"])
	print("missing string bytes:", result["total_missing_string_bytes"])
	print("fits holes + free banks:", result["combined_fits_contexts"])
	print("combined failed:", result["combined_failed_contexts"])
	print("combined missing bytes:", result["combined_missing_string_bytes"])
	print("output:", OUT)


if __name__ == "__main__":
	main()
