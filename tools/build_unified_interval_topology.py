#!/usr/bin/env python3
"""Build a conservative union of every primary and overlay CD_READ interval."""

import json
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TRACE = ROOT / "translation" / "cd_read_trace.tsv"
OUT = ROOT / "translation" / "unified_interval_topology.json"
SECTOR = 2048
DATA_TRACK_OFFSET = 7_914_480
PAYLOAD_START = 162
PAYLOAD_END = 5474  # end of overlay physical grid 53 (LBA 5378 + 96)
SIDECAR_START = 9178
SIDECAR_END = 9328


def merge(intervals):
	merged = []
	for start, end, owner in sorted(intervals):
		if not merged or start > merged[-1][1]:
			merged.append([start, end, {owner}])
		else:
			merged[-1][1] = max(merged[-1][1], end)
			merged[-1][2].add(owner)
	return merged


def complement(merged, start, end):
	holes = []
	pos = start
	for left, right, _ in merged:
		if right <= start or left >= end:
			continue
		left, right = max(left, start), min(right, end)
		if pos < left:
			holes.append((pos, left))
		pos = max(pos, right)
	if pos < end:
		holes.append((pos, end))
	return holes


def main():
	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	intervals = []
	seen = set()
	for entry in primary["logical_entries"]:
		if entry["physical_grid"] is None:
			continue
		key = (entry["lba"], entry["load_sectors"])
		if key not in seen:
			intervals.append((key[0], key[0] + key[1], "primary"))
			seen.add(key)
	seen.clear()
	for entry in overlay["entries"]:
		key = (entry["lba"], entry["load_sectors"])
		if key not in seen:
			intervals.append((key[0], key[0] + key[1], "overlay"))
			seen.add(key)
	if TRACE.exists():
		with TRACE.open(encoding="utf-8", newline="") as source:
			for row in csv.DictReader(source, delimiter="\t"):
				start, count = int(row["lba"]), int(row["count"])
				if count:
					intervals.append((start, start + count, "runtime-trace"))

	merged = merge(intervals)
	holes = complement(merged, PAYLOAD_START, PAYLOAD_END)
	zero_sector_runs = []
	with BIN.open("rb") as source:
		for gap_start, gap_end in holes:
			run_start = None
			for lba in range(gap_start, gap_end):
				source.seek(DATA_TRACK_OFFSET + lba * SECTOR)
				sector = source.read(SECTOR)
				is_fill = sector == bytes(SECTOR) or sector == bytes((0xFF,)) * SECTOR
				if is_fill and run_start is None:
					run_start = lba
				if not is_fill and run_start is not None:
					zero_sector_runs.append((run_start, lba))
					run_start = None
			if run_start is not None:
				zero_sector_runs.append((run_start, gap_end))
	result = {
		"format": "UNIFIED-INTERVAL-TOPOLOGY",
		"version": 1,
		"policy": "Any sector loaded by either topology is live; internal zero/FF bytes are not holes.",
		"payload_range_lba": [PAYLOAD_START, PAYLOAD_END],
		"merged_live_intervals": [
			{"start_lba": a, "end_lba": b, "sectors": b - a,
			 "owners": sorted(owners)} for a, b, owners in merged
			if b > PAYLOAD_START and a < PAYLOAD_END
		],
		"common_unloaded_gaps": [
			{"start_lba": a, "end_lba": b, "sectors": b - a,
			 "bytes": (b - a) * SECTOR,
			 "unclassified_translation_sources": sum(
				a * SECTOR <= x["source_iso_offset"] < b * SECTOR
				for x in overlay.get("unclassified_sources", []))}
			for a, b in holes
		],
		"common_gap_sectors": sum(b - a for a, b in holes),
		"largest_common_gap_sectors": max((b - a for a, b in holes), default=0),
		"fill_sector_candidates_not_runtime_verified": [
			{"start_lba": a, "end_lba": b, "sectors": b - a,
			 "bytes": (b - a) * SECTOR} for a, b in zero_sector_runs
		],
		"fill_candidate_sectors": sum(b - a for a, b in zero_sector_runs),
		"verified_sidecar": {
			"start_lba": SIDECAR_START, "end_lba": SIDECAR_END,
			"sectors": SIDECAR_END - SIDECAR_START,
			"bytes": (SIDECAR_END - SIDECAR_START) * SECTOR,
		},
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("merged live intervals:", len(result["merged_live_intervals"]))
	print("common unloaded gaps:", len(holes))
	print("common gap sectors:", result["common_gap_sectors"])
	print("largest common gap sectors:", result["largest_common_gap_sectors"])
	print("00/FF candidate sectors:", result["fill_candidate_sectors"])
	print("verified sidecar sectors:", SIDECAR_END - SIDECAR_START)
	print("output:", OUT)


if __name__ == "__main__":
	main()
