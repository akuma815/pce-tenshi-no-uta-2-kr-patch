# -*- coding: utf-8 -*-
"""Map logical $54A5 area entries to physical 96-sector grid blocks."""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO_PATH = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
OUT_PATH = os.path.join(GAME_DIR, "translation", "slot_topology.json")

TABLE_OFFSET = 0x424A5
ENTRY_COUNT = 55
GRID_BASE_LBA = 162
GRID_SECTORS = 96
GRID_COUNT = 55


def main():
    with open(ISO_PATH, "rb") as f:
        f.seek(TABLE_OFFSET)
        table = f.read(ENTRY_COUNT * 4)

    row_offsets_by_grid = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["번역"].strip() and row["영역"].startswith("slot"):
                row_offsets_by_grid[int(row["영역"][4:6])].append(
                    int(row["키(ISO오프셋)"], 16))

    physical = {
        i: {"grid": i, "lba": GRID_BASE_LBA + GRID_SECTORS * i,
            "logical_entries": [], "load_counts": [],
            "translated_rows": 0, "tail_translated_rows": 0}
        for i in range(GRID_COUNT)
    }
    logical = []
    for index in range(ENTRY_COUNT):
        entry = table[index * 4:index * 4 + 4]
        lba = (entry[0] << 16) | (entry[1] << 8) | entry[2]
        count = entry[3]
        delta = lba - GRID_BASE_LBA
        grid = delta // GRID_SECTORS if delta >= 0 and delta % GRID_SECTORS == 0 else None
        valid = grid is not None and 0 <= grid < GRID_COUNT
        logical.append({"logical_entry": index, "lba": lba,
                        "load_sectors": count, "physical_grid": grid if valid else None})
        if valid:
            physical[grid]["logical_entries"].append(index)
            physical[grid]["load_counts"].append(count)

    mapped = [v for v in physical.values() if v["logical_entries"]]
    for value in mapped:
        load_bytes = value["load_counts"][0] * 2048
        base = value["lba"] * 2048
        offsets = row_offsets_by_grid.get(value["grid"], [])
        value["translated_rows"] = sum(base <= x < base + load_bytes for x in offsets)
        value["tail_translated_rows"] = len(offsets) - value["translated_rows"]
    unmapped_with_text = [v for v in physical.values()
                          if not v["logical_entries"] and row_offsets_by_grid.get(v["grid"])]
    for value in unmapped_with_text:
        value["tail_translated_rows"] = len(row_offsets_by_grid[value["grid"]])
    inconsistent = [v for v in mapped if len(set(v["load_counts"])) != 1]
    if inconsistent:
        raise ValueError(f"same physical grid has inconsistent load counts: {inconsistent}")

    result = {
        "table_offset": TABLE_OFFSET,
        "logical_entries": logical,
        "physical_grids": list(physical.values()),
        "mapped_grid_count": len(mapped),
        "unmapped_text_grid_count": len(unmapped_with_text),
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"mapped physical grids: {len(mapped)}")
    for v in mapped:
        print(f"  grid{v['grid']:02d} LBA {v['lba']:4d} load {v['load_counts'][0]:2d} "
              f"logical={v['logical_entries']} translated_rows={v['translated_rows']}")
    print(f"unmapped grids containing translated rows: {len(unmapped_with_text)}")
    print(" ".join(f"{v['grid']:02d}({v['tail_translated_rows']})" for v in unmapped_with_text))
    print(f"report: {OUT_PATH}")


if __name__ == "__main__":
    main()
