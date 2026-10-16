#!/usr/bin/env python3
"""Classify translated sources against primary and second-engine overlay loaders."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
TSV = ROOT / "translation" / "script_sheet.tsv"
PRIMARY = ROOT / "translation" / "slot_topology.json"
OUT = ROOT / "translation" / "overlay_topology.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
TABLE_OFFSET = 0x83531
ENTRY_COUNT = 55
OVERLAY_BASE_LBA = 290
GRID_SECTORS = 96


def contains(entry, source):
	start = entry["lba"] * SECTOR
	return start <= source < start + entry["load_sectors"] * SECTOR


def main():
	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	primary_entries = [
		{"logical_entry": x["logical_entry"], "lba": x["lba"],
		 "load_sectors": x["load_sectors"], "physical_grid": x["physical_grid"]}
		for x in primary["logical_entries"] if x["physical_grid"] is not None
	]

	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + TABLE_OFFSET)
		table = source.read(ENTRY_COUNT * 4)
	assert len(table) == ENTRY_COUNT * 4
	overlay_entries = []
	for index in range(ENTRY_COUNT):
		record = table[index * 4:index * 4 + 4]
		lba = record[0] << 16 | record[1] << 8 | record[2]
		count = record[3]
		delta = lba - OVERLAY_BASE_LBA
		grid = delta // GRID_SECTORS if delta >= 0 and delta % GRID_SECTORS == 0 else None
		assert grid is not None and 0 <= grid < 55
		overlay_entries.append({
			"logical_entry": index, "lba": lba, "load_sectors": count,
			"physical_grid": grid,
		})

	rows = []
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			if not row["번역"].strip():
				continue
			offset = int(row["키(ISO오프셋)"], 16)
			p = sorted({x["logical_entry"] for x in primary_entries if contains(x, offset)})
			o = sorted({x["logical_entry"] for x in overlay_entries if contains(x, offset)})
			rows.append({
				"source_iso_offset": offset,
				"legacy_region": row["영역"],
				"primary_logical_entries": p,
				"overlay_logical_entries": o,
			})

	classes = defaultdict(int)
	for row in rows:
		p, o = bool(row["primary_logical_entries"]), bool(row["overlay_logical_entries"])
		classes["both" if p and o else "primary_only" if p else "overlay_only" if o else "unclassified"] += 1

	by_grid = []
	for grid in sorted({x["physical_grid"] for x in overlay_entries}):
		entries = [x for x in overlay_entries if x["physical_grid"] == grid]
		matched = [r for r in rows if any(x["logical_entry"] in r["overlay_logical_entries"] for x in entries)]
		if matched:
			by_grid.append({
				"physical_grid": grid,
				"lba": entries[0]["lba"],
				"logical_entries": [x["logical_entry"] for x in entries],
				"load_sectors": entries[0]["load_sectors"],
				"translated_rows": len(matched),
				"overlay_only_rows": sum(not x["primary_logical_entries"] for x in matched),
			})

	first = next(x for x in rows if x["source_iso_offset"] == 0x10B9E8)
	assert first["overlay_logical_entries"] == [2]
	assert not first["primary_logical_entries"]
	result = {
		"format": "OVERLAY-TOPOLOGY",
		"version": 1,
		"table_offset": TABLE_OFFSET,
		"base_lba": OVERLAY_BASE_LBA,
		"entry_count": ENTRY_COUNT,
		"entries": overlay_entries,
		"classification_counts": dict(classes),
		"translated_rows": len(rows),
		"physical_grids_with_translations": by_grid,
		"first_dialogue_evidence": first,
		"unclassified_sources": [
			{"source_iso_offset": x["source_iso_offset"], "legacy_region": x["legacy_region"]}
			for x in rows if not x["primary_logical_entries"] and not x["overlay_logical_entries"]
		],
		"runtime_cd_read": {"frame": 1269, "lba": 482, "count": 96,
		                    "end": 578, "dest_bank": "0x68", "mode": "0x06"},
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("translated rows:", len(rows))
	for key in ("primary_only", "overlay_only", "both", "unclassified"):
		print(f"{key}:", classes[key])
	print("overlay grids with translations:", len(by_grid))
	print("output:", OUT)


if __name__ == "__main__":
	main()
