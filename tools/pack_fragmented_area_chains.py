# -*- coding: utf-8 -*-
"""Allocate overflow-area strings as bank-local continuation chains (dry run).

Intermediate segments reserve four bytes for: 02, bank-index, address-low,
address-high.  The future fetch hook consumes this marker and switches streams.
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
OUT_DIR = os.path.join(GAME_DIR, "translation", "fragmented_area_chains")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
AREA_BYTES = 96 * SECTOR_SIZE
REDIRECT_SIZE = 5
CHAIN_MARKER_SIZE = 4
TARGET_GRIDS = (15, 28, 40)


def merge_ranges(ranges):
    out = []
    for start, end in sorted(ranges):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def split_banks(ranges):
    out = []
    for start, end in ranges:
        while start < end:
            stop = min(end, ((start // BANK_SIZE) + 1) * BANK_SIZE)
            if stop > start:
                out.append([start, stop])
            start = stop
    return out


def take_whole(free_ranges, size):
    fits = [(end - start, i) for i, (start, end) in enumerate(free_ranges)
            if end - start >= size]
    if not fits:
        return None
    _, i = min(fits)
    start, end = free_ranges[i]
    free_ranges[i] = [start + size, end]
    if free_ranges[i][0] == free_ranges[i][1]:
        free_ranges.pop(i)
    return start


def take_largest_segment(free_ranges, remaining_size):
    candidates = [(end - start, i) for i, (start, end) in enumerate(free_ranges)
                  if end - start > CHAIN_MARKER_SIZE]
    if not candidates:
        return None
    length, i = max(candidates)
    start, _ = free_ranges.pop(i)
    data_size = min(remaining_size - 1, length - CHAIN_MARKER_SIZE)
    if data_size <= 0:
        return None
    unused_start = start + data_size + CHAIN_MARKER_SIZE
    if unused_start < start + length:
        free_ranges.append([unused_start, start + length])
    return start, data_size


def allocate_chain(free_ranges, data):
    segments = []
    cursor = 0
    while cursor < len(data):
        whole = take_whole(free_ranges, len(data) - cursor)
        if whole is not None:
            segments.append({"offset": whole, "data": data[cursor:], "final": True})
            return segments
        piece = take_largest_segment(free_ranges, len(data) - cursor)
        if piece is None:
            return None
        start, size = piece
        segments.append({"offset": start, "data": data[cursor:cursor + size], "final": False})
        cursor += size
    raise AssertionError("chain ended without final segment")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    iso = open(ISO_PATH, "rb").read()
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        topology = json.load(f)
    topology = {x["grid"]: x for x in topology["physical_grids"]}

    rows = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            region = row["영역"]
            if row["번역"].strip() and region.startswith("slot"):
                grid = int(region[4:6])
                if grid in TARGET_GRIDS:
                    rows[grid].append((int(row["키(ISO오프셋)"], 16), row["번역"].strip()))

    success = []
    failed = []
    for number in TARGET_GRIDS:
        grid = topology[number]
        area_start = grid["lba"] * SECTOR_SIZE
        live_end = area_start + grid["load_counts"][0] * SECTOR_SIZE
        load_sectors = grid["load_counts"][0]
        holes = [[load_sectors * SECTOR_SIZE, AREA_BYTES]]
        encoded_rows = []
        for source_offset, text in rows[number]:
            if not area_start <= source_offset < live_end:
                continue
            end = iso.find(b"\x00", source_offset, min(len(iso), source_offset + SECTOR_SIZE)) + 1
            if end <= source_offset:
                raise ValueError(f"grid{number:02d}: unterminated source")
            rel_start = source_offset - area_start
            rel_end = end - area_start
            if rel_end == AREA_BYTES + 1 and iso[end - 1] == 0:
                rel_end = AREA_BYTES
            if not (0 <= rel_start < rel_end <= AREA_BYTES):
                raise ValueError(f"grid{number:02d}: source outside area")
            holes.append([rel_start + REDIRECT_SIZE, rel_end])
            encoded_rows.append((source_offset, encode_string(text, char_map) + b"\x00"))

        free_ranges = split_banks(merge_ranges(holes))
        initial_free = sum(b - a for a, b in free_ranges)
        unique = sorted({data for _, data in encoded_rows}, key=len, reverse=True)
        chains = {}
        for data in unique:
            chain = allocate_chain(free_ranges, data)
            if chain is None:
                failed.append({
                    "physical_grid": number,
                    "placed_strings": len(chains),
                    "total_strings": len(unique),
                    "unplaced_bytes": sum(len(x) for x in unique if x not in chains),
                    "remaining_bytes": sum(b - a for a, b in free_ranges),
                })
                break
            chains[data] = chain
        else:
            serial_chains = []
            total_markers = 0
            for data, chain in chains.items():
                total_markers += len(chain) - 1
                serial_chains.append({
                    "source_data_hex": data.hex(),
                    "segments": [
                        {"area_relative_offset": s["offset"], "data_hex": s["data"].hex(),
                         "data_length": len(s["data"]), "final": s["final"]}
                        for s in chain
                    ],
                })
            first_offset = {data: chain[0]["offset"] for data, chain in chains.items()}
            layout = {
                "format": "KAC1",
                "physical_grid": number,
                "lba": grid["lba"],
                "logical_entries": grid["logical_entries"],
                "original_load_sectors": load_sectors,
                "extended_load_sectors": 96,
                "initial_free_bytes": initial_free,
                "remaining_free_bytes": sum(b - a for a, b in free_ranges),
                "continuation_markers": total_markers,
                "chains": serial_chains,
                "redirects": {
                    f"{source_offset:07x}": {"area_relative_target": first_offset[data]}
                    for source_offset, data in encoded_rows
                },
            }
            with open(os.path.join(OUT_DIR, f"grid{number:02d}_chains.json"), "w", encoding="utf-8") as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)
            success.append(layout)

    print(f"successful chain layouts: {len(success)}")
    for x in success:
        print(f'  grid{x["physical_grid"]:02d}: markers={x["continuation_markers"]}, '
              f'remaining={x["remaining_free_bytes"]} B')
    print("failed chain layouts:")
    for x in failed:
        print(f'  grid{x["physical_grid"]:02d}: placed {x["placed_strings"]}/{x["total_strings"]}, '
              f'unplaced={x["unplaced_bytes"]} B, remaining={x["remaining_bytes"]} B')
    print("output:", OUT_DIR)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
