# -*- coding: utf-8 -*-
"""Build dry-run string packages for physical area grids referenced by $54A5.

This tool never modifies the ISO.  It consumes slot_topology.json, emits only
packages that fit within the area's 96-sector physical block, and rejects overflow.
"""
from __future__ import annotations

import csv
import json
import math
import os
import struct
import sys
import zlib
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tools"))
from patch_iso import encode_string

TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
TOPOLOGY_PATH = os.path.join(GAME_DIR, "translation", "slot_topology.json")
OUT_DIR = os.path.join(GAME_DIR, "translation", "mapped_area_packages")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
MAX_SECTORS = 96
MAX_BYTES = MAX_SECTORS * SECTOR_SIZE
HEADER_SIZE = 32


def append_bank_safe(pool, encoded, absolute_start):
    absolute = absolute_start + len(pool)
    in_bank = absolute % BANK_SIZE
    if in_bank + len(encoded) > BANK_SIZE:
        pool.extend(b"\x00" * (BANK_SIZE - in_bank))
    relative = HEADER_SIZE + len(pool)
    pool.extend(encoded)
    return relative


def load_rows():
    rows = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            region = row["영역"]
            ko = row["번역"].strip()
            if ko and region.startswith("slot"):
                rows[int(region[4:6])].append({
                    "source_offset": int(row["키(ISO오프셋)"], 16),
                    "text": ko,
                })
    return rows


def build_package(grid, rows, char_map):
    load_sectors = grid["load_counts"][0]
    package_offset = load_sectors * SECTOR_SIZE
    pool = bytearray()
    encoded_to_relative = {}
    redirects = {}

    # Longest-first ordering reduces the chance of wasting a bank tail.
    encoded_rows = [
        (row["source_offset"], encode_string(row["text"], char_map) + b"\x00")
        for row in rows
    ]
    unique = sorted({data for _, data in encoded_rows}, key=len, reverse=True)
    for data in unique:
        encoded_to_relative[data] = append_bank_safe(
            pool, data, package_offset + HEADER_SIZE)
    for source_offset, data in encoded_rows:
        rel = encoded_to_relative[data]
        redirects[f"{source_offset:07x}"] = {
            "package_relative_offset": rel,
            "area_relative_offset": package_offset + rel,
            "length": len(data),
        }

    header = struct.pack(
        "<4sBBHIIIIII",
        b"KAP1", 1, grid["grid"], 0,
        HEADER_SIZE, len(pool), len(unique), len(redirects),
        zlib.crc32(pool) & 0xFFFFFFFF, 0,
    )
    assert len(header) == HEADER_SIZE
    blob = header + pool
    needed_bytes = package_offset + len(blob)
    return blob, redirects, len(unique), package_offset, needed_bytes


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # Avoid stale manifests from an earlier classification entering normalization.
    for name in os.listdir(OUT_DIR):
        if name.startswith("grid") and (name.endswith(".json") or name.endswith(".bin")):
            os.unlink(os.path.join(OUT_DIR, name))
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        topology = json.load(f)
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)
    rows_by_grid = load_rows()

    emitted = []
    rejected = []
    for grid in topology["physical_grids"]:
        number = grid["grid"]
        rows = rows_by_grid.get(number, [])
        if not grid["logical_entries"] or not rows:
            continue
        if len(set(grid["load_counts"])) != 1:
            raise ValueError(f"grid{number:02d}: inconsistent load counts")
        live_start = grid["lba"] * SECTOR_SIZE
        live_end = live_start + grid["load_counts"][0] * SECTOR_SIZE
        rows = [row for row in rows if live_start <= row["source_offset"] < live_end]
        if not rows:
            continue

        blob, redirects, unique_count, package_offset, needed_bytes = build_package(
            grid, rows, char_map)
        needed_sectors = math.ceil(needed_bytes / SECTOR_SIZE)
        if needed_bytes > MAX_BYTES:
            rejected.append({
                "physical_grid": number,
                "lba": grid["lba"],
                "needed_sectors": needed_sectors,
                "overflow_bytes": needed_bytes - MAX_BYTES,
            })
            continue

        stem = f"grid{number:02d}_area_strings"
        with open(os.path.join(OUT_DIR, stem + ".bin"), "wb") as f:
            f.write(blob)
        manifest = {
            "format": "KAP1",
            "version": 1,
            "physical_grid": number,
            "lba": grid["lba"],
            "logical_entries": grid["logical_entries"],
            "original_load_sectors": grid["load_counts"][0],
            "package_area_offset": package_offset,
            "package_bytes": len(blob),
            "needed_sectors": needed_sectors,
            "unique_strings": unique_count,
            "source_redirects": redirects,
            "source_live_range": [live_start, live_end],
        }
        with open(os.path.join(OUT_DIR, stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        emitted.append(manifest)

    summary = {
        "format": "KAP1-build-summary",
        "emitted_grids": [x["physical_grid"] for x in emitted],
        "rejected": rejected,
    }
    with open(os.path.join(OUT_DIR, "build_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"emitted mapped area packages: {len(emitted)}")
    for x in emitted:
        print(f'  grid{x["physical_grid"]:02d} LBA {x["lba"]}: '
              f'{x["package_bytes"]} B, need {x["needed_sectors"]} sectors, '
              f'logical={x["logical_entries"]}')
    print("rejected mapped grids:")
    for x in rejected:
        print(f'  grid{x["physical_grid"]:02d}: need {x["needed_sectors"]} sectors, '
              f'overflow {x["overflow_bytes"]} B')
    print("output:", OUT_DIR)
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
