# -*- coding: utf-8 -*-
"""Dry-run allocator using reclaimed original-string holes plus slot tail padding.

No ISO bytes are changed.  Successful layouts map every source offset to a translated
string placed wholly inside one 8 KiB bank of the same 96-sector slot.
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
OUT_DIR = os.path.join(GAME_DIR, "translation", "slot_hole_layouts")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
SLOT_SIZE = 96 * SECTOR_SIZE
SLOT_TABLE_OFFSET = 0x424A5
SLOT_COUNT = 55
REDIRECT_SIZE = 5


def split_at_banks(start, end):
    pieces = []
    while start < end:
        boundary = ((start // BANK_SIZE) + 1) * BANK_SIZE
        stop = min(end, boundary)
        if stop > start:
            pieces.append([start, stop])
        start = stop
    return pieces


def allocate_best_fit(free_ranges, data):
    candidates = [(b - a, i, a, b) for i, (a, b) in enumerate(free_ranges)
                  if b - a >= len(data)]
    if not candidates:
        return None
    _, i, start, end = min(candidates)
    free_ranges[i] = [start + len(data), end]
    if free_ranges[i][0] == free_ranges[i][1]:
        free_ranges.pop(i)
    return start


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    iso = open(ISO_PATH, "rb").read()
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)

    with open(ISO_PATH, "rb") as f:
        f.seek(SLOT_TABLE_OFFSET)
        table = f.read(SLOT_COUNT * 4)
    slot_counts = [table[i * 4 + 3] for i in range(SLOT_COUNT)]
    slot_lbas = [
        (table[i * 4] << 16) | (table[i * 4 + 1] << 8) | table[i * 4 + 2]
        for i in range(SLOT_COUNT)
    ]

    rows_by_slot = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            region = row["영역"]
            ko = row["번역"].strip()
            if ko and region.startswith("slot"):
                rows_by_slot[int(region[4:6])].append(
                    (int(row["키(ISO오프셋)"], 16), ko))

    success = []
    failed = []
    for slot, rows in sorted(rows_by_slot.items()):
        slot_file_start = slot_lbas[slot] * SECTOR_SIZE
        intervals = []
        source_data = []
        for source_offset, text in rows:
            end = iso.find(b"\x00", source_offset, min(len(iso), source_offset + SECTOR_SIZE))
            if end < source_offset:
                raise ValueError(f"slot{slot:02d}: unterminated source at {source_offset:#x}")
            end += 1
            length = end - source_offset
            if length < REDIRECT_SIZE:
                raise ValueError(f"slot{slot:02d}: source too short for redirect at {source_offset:#x}")
            rel_start = source_offset - slot_file_start
            rel_end = end - slot_file_start
            if not (0 <= rel_start < rel_end <= SLOT_SIZE):
                raise ValueError(f"slot{slot:02d}: source outside slot at {source_offset:#x}")
            intervals.append((rel_start, rel_end))
            source_data.append((source_offset, encode_string(text, char_map) + b"\x00"))

        # Every source becomes a 5-byte redirect; the remainder is reusable.
        free_ranges = []
        for start, end in intervals:
            free_ranges.extend(split_at_banks(start + REDIRECT_SIZE, end))
        tail_start = slot_counts[slot] * SECTOR_SIZE
        free_ranges.extend(split_at_banks(tail_start, SLOT_SIZE))

        unique = {}
        for _, data in source_data:
            unique.setdefault(data, None)
        for data in sorted(unique, key=len, reverse=True):
            pos = allocate_best_fit(free_ranges, data)
            if pos is None:
                break
            unique[data] = pos

        unplaced = [data for data, pos in unique.items() if pos is None]
        if unplaced:
            failed.append({
                "slot": slot,
                "unplaced_strings": len(unplaced),
                "unplaced_bytes": sum(map(len, unplaced)),
                "largest_unplaced": max(map(len, unplaced)),
                "free_bytes_fragmented": sum(b - a for a, b in free_ranges),
            })
            continue

        redirects = {
            f"{source_offset:07x}": {
                "slot_relative_target": unique[data],
                "length": len(data),
            }
            for source_offset, data in source_data
        }
        layout = {
            "format": "KSH1",
            "slot": slot,
            "original_sectors": slot_counts[slot],
            "unique_strings": len(unique),
            "source_count": len(source_data),
            "placements": [
                {"slot_relative_offset": pos, "data_hex": data.hex(), "length": len(data)}
                for data, pos in sorted(unique.items(), key=lambda x: x[1])
            ],
            "redirects": redirects,
        }
        path = os.path.join(OUT_DIR, f"slot{slot:02d}_hole_layout.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(layout, f, ensure_ascii=False, indent=2)
        success.append((slot, len(unique), len(source_data)))

    print(f"successful hole layouts: {len(success)}")
    print(" ".join(f"{slot:02d}" for slot, _, _ in success))
    print("failed layouts:")
    for x in failed:
        print(f"  slot{x['slot']:02d}: {x['unplaced_strings']} strings / "
              f"{x['unplaced_bytes']} B unplaced, largest {x['largest_unplaced']} B, "
              f"fragmented free {x['free_bytes_fragmented']} B")
    print(f"output: {OUT_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
