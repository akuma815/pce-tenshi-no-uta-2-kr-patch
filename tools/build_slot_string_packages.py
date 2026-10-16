# -*- coding: utf-8 -*-
"""Build dry-run per-slot translated string packages (no ISO mutation).

Only slots that fit in the 96-sector area are emitted.  Each string is kept inside
one 8 KiB physical bank so the future fetch hook never needs cross-bank logic.
"""
from __future__ import annotations

import csv
import json
import os
import struct
import sys
import zlib
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tools"))
from patch_iso import encode_string

ISO_PATH = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
OUT_DIR = os.path.join(GAME_DIR, "translation", "slot_packages")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
SLOT_SECTORS = 96
SLOT_BYTES = SLOT_SECTORS * SECTOR_SIZE
SLOT_TABLE_OFFSET = 0x424A5
SLOT_COUNT = 55
HEADER_SIZE = 32


def load_rows():
    grouped = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ko = row["번역"].strip()
            region = row["영역"]
            if ko and region.startswith("slot"):
                grouped[region].append((int(row["키(ISO오프셋)"], 16), ko))
    return grouped


def load_slot_counts():
    with open(ISO_PATH, "rb") as f:
        f.seek(SLOT_TABLE_OFFSET)
        table = f.read(SLOT_COUNT * 4)
    return [table[i * 4 + 3] for i in range(SLOT_COUNT)]


def append_bank_safe(pool, encoded, package_start):
    absolute = package_start + HEADER_SIZE + len(pool)
    in_bank = absolute % BANK_SIZE
    if in_bank + len(encoded) > BANK_SIZE:
        pool.extend(b"\x00" * (BANK_SIZE - in_bank))
    relative = HEADER_SIZE + len(pool)
    pool.extend(encoded)
    return relative


def build_one(slot, original_sectors, rows, char_map):
    package_start = original_sectors * SECTOR_SIZE
    pool = bytearray()
    by_encoded = {}
    redirects = {}

    for source_offset, text in rows:
        encoded = encode_string(text, char_map) + b"\x00"
        relative = by_encoded.get(encoded)
        if relative is None:
            relative = append_bank_safe(pool, encoded, package_start)
            by_encoded[encoded] = relative
        redirects[f"{source_offset:07x}"] = {
            "package_relative_offset": relative,
            "slot_relative_offset": package_start + relative,
            "length": len(encoded),
        }

    header = struct.pack(
        "<4sBBHIIIIII",
        b"KSP1", 1, slot, 0,
        HEADER_SIZE, len(pool), len(by_encoded), len(redirects),
        zlib.crc32(pool) & 0xFFFFFFFF, 0,
    )
    assert len(header) == HEADER_SIZE
    blob = header + pool
    needed = package_start + len(blob)
    return blob, redirects, len(by_encoded), needed


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)
    rows_by_region = load_rows()
    slot_counts = load_slot_counts()

    emitted = []
    rejected = []
    for slot in range(SLOT_COUNT):
        region = f"slot{slot:02d}"
        rows = rows_by_region.get(region, [])
        if not rows:
            continue
        blob, redirects, unique_count, needed_bytes = build_one(
            slot, slot_counts[slot], rows, char_map)
        needed_sectors = (needed_bytes + SECTOR_SIZE - 1) // SECTOR_SIZE
        if needed_bytes > SLOT_BYTES:
            rejected.append((slot, needed_sectors, needed_bytes - SLOT_BYTES))
            continue

        stem = f"slot{slot:02d}_strings"
        with open(os.path.join(OUT_DIR, stem + ".bin"), "wb") as f:
            f.write(blob)
        manifest = {
            "format": "KSP1",
            "slot": slot,
            "original_sectors": slot_counts[slot],
            "package_offset": slot_counts[slot] * SECTOR_SIZE,
            "package_bytes": len(blob),
            "needed_sectors": needed_sectors,
            "unique_strings": unique_count,
            "source_redirects": redirects,
        }
        with open(os.path.join(OUT_DIR, stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        emitted.append((slot, len(blob), needed_sectors, unique_count, len(redirects)))

    print("emitted slot packages:")
    for x in emitted:
        print(f"  slot{x[0]:02d}: {x[1]:5d} B, need {x[2]:2d} sectors, "
              f"{x[3]} unique / {x[4]} sources")
    print("rejected slots (no files emitted):")
    for x in rejected:
        print(f"  slot{x[0]:02d}: need {x[1]} sectors, overflow {x[2]} B")
    print(f"output: {OUT_DIR}")
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
