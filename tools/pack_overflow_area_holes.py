# -*- coding: utf-8 -*-
"""Dry-run hole allocator for mapped area grids that exceed 96 sectors.

Original strings are reduced to five-byte redirects; their remaining bytes and the
unused tail after the loader's sector count become placement ranges.  ISO is untouched.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tools"))
from patch_iso import encode_string

ISO_PATH = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
TOPOLOGY_PATH = os.path.join(GAME_DIR, "translation", "slot_topology.json")
AUDIT_PATH = os.path.join(GAME_DIR, "translation", "mapped_area_package_report.tsv")
OUT_DIR = os.path.join(GAME_DIR, "translation", "overflow_area_hole_layouts")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
AREA_SECTORS = 96
AREA_BYTES = AREA_SECTORS * SECTOR_SIZE
REDIRECT_SIZE = 5


def split_banks(start, end):
    out = []
    while start < end:
        stop = min(end, ((start // BANK_SIZE) + 1) * BANK_SIZE)
        if stop > start:
            out.append([start, stop])
        start = stop
    return out


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def best_fit(free_ranges, size):
    candidates = [(end - start, i, start, end)
                  for i, (start, end) in enumerate(free_ranges)
                  if end - start >= size]
    if not candidates:
        return None
    _, index, start, end = min(candidates)
    free_ranges[index] = [start + size, end]
    if free_ranges[index][0] == free_ranges[index][1]:
        free_ranges.pop(index)
    return start


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    iso = open(ISO_PATH, "rb").read()
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        topology = json.load(f)

    overflow_grids = set()
    with open(AUDIT_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["string_status"] == "OVERFLOW":
                overflow_grids.add(int(row["physical_grid"]))

    rows_by_grid = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            region = row["영역"]
            ko = row["번역"].strip()
            if ko and region.startswith("slot"):
                grid = int(region[4:6])
                if grid in overflow_grids:
                    rows_by_grid[grid].append(
                        (int(row["키(ISO오프셋)"], 16), ko))

    topology_by_grid = {x["grid"]: x for x in topology["physical_grids"]}
    successes = []
    failures = []
    for number in sorted(overflow_grids):
        grid = topology_by_grid[number]
        load_sectors = grid["load_counts"][0]
        area_file_start = grid["lba"] * SECTOR_SIZE
        live_end = area_file_start + grid["load_counts"][0] * SECTOR_SIZE
        holes = []
        encoded_rows = []

        for source_offset, text in rows_by_grid[number]:
            if not area_file_start <= source_offset < live_end:
                continue
            end = iso.find(b"\x00", source_offset, min(len(iso), source_offset + SECTOR_SIZE))
            if end < 0:
                raise ValueError(f"grid{number:02d}: unterminated source {source_offset:#x}")
            end += 1
            source_length = end - source_offset
            if source_length < REDIRECT_SIZE:
                raise ValueError(f"grid{number:02d}: source shorter than redirect {source_offset:#x}")
            rel_start = source_offset - area_file_start
            rel_end = end - area_file_start
            # One verified grid28 string uses the final 108 bytes of the area
            # and stores only its terminating NUL at the next block's byte 0.
            # Keep that external NUL untouched and reclaim only in-area bytes.
            if rel_end == AREA_BYTES + 1 and iso[end - 1] == 0:
                rel_end = AREA_BYTES
            if not (0 <= rel_start < rel_end <= AREA_BYTES):
                raise ValueError(f"grid{number:02d}: source outside physical area {source_offset:#x}")
            holes.append([rel_start + REDIRECT_SIZE, rel_end])
            encoded_rows.append((source_offset, encode_string(text, char_map) + b"\x00"))

        # The loader may safely be extended up to the fixed 96-sector area limit.
        holes.append([load_sectors * SECTOR_SIZE, AREA_BYTES])
        free_ranges = []
        for start, end in merge_ranges(holes):
            free_ranges.extend(split_banks(start, end))
        initial_free = sum(end - start for start, end in free_ranges)

        unique = {data for _, data in encoded_rows}
        placements = {}
        for data in sorted(unique, key=len, reverse=True):
            position = best_fit(free_ranges, len(data))
            if position is None:
                failures.append({
                    "physical_grid": number,
                    "unplaced_strings": sum(x not in placements for x in unique),
                    "unplaced_bytes": sum(len(x) for x in unique if x not in placements),
                    "remaining_fragmented_bytes": sum(b - a for a, b in free_ranges),
                    "initial_free_bytes": initial_free,
                })
                break
            placements[data] = position
        else:
            redirects = {
                f"{source_offset:07x}": {
                    "area_relative_target": placements[data],
                    "length": len(data),
                }
                for source_offset, data in encoded_rows
            }
            layout = {
                "format": "KAH1",
                "physical_grid": number,
                "lba": grid["lba"],
                "logical_entries": grid["logical_entries"],
                "original_load_sectors": load_sectors,
                "extended_load_sectors": AREA_SECTORS,
                "initial_free_bytes": initial_free,
                "remaining_free_bytes": sum(b - a for a, b in free_ranges),
                "unique_strings": len(unique),
                "placements": [
                    {"area_relative_offset": pos, "length": len(data), "data_hex": data.hex()}
                    for data, pos in sorted(placements.items(), key=lambda x: x[1])
                ],
                "redirects": redirects,
            }
            path = os.path.join(OUT_DIR, f"grid{number:02d}_hole_layout.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)
            successes.append(layout)

    print(f"successful overflow layouts: {len(successes)}")
    for x in successes:
        print(f'  grid{x["physical_grid"]:02d}: {x["unique_strings"]} strings, '
              f'free {x["initial_free_bytes"]} -> {x["remaining_free_bytes"]} B')
    print("failed overflow layouts:")
    for x in failures:
        print(f'  grid{x["physical_grid"]:02d}: {x["unplaced_strings"]} strings / '
              f'{x["unplaced_bytes"]} B unplaced; fragmented {x["remaining_fragmented_bytes"]} B')
    print("output:", OUT_DIR)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
