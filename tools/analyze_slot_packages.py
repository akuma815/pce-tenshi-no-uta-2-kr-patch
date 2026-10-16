# -*- coding: utf-8 -*-
"""Audit the redesigned per-slot Korean package sizes without modifying the ISO.

The report answers the first redesign question: can each area's translated strings
and local glyph subset fit inside its existing 96-sector slot?
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(GAME_DIR, "tools")
sys.path.insert(0, TOOLS_DIR)

from patch_iso import encode_string  # reuse the game's exact markup encoder

ISO_PATH = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
REPORT_PATH = os.path.join(GAME_DIR, "translation", "slot_package_report.tsv")

SECTOR_SIZE = 2048
SLOT_SECTORS = 96
SLOT_BYTES = SLOT_SECTORS * SECTOR_SIZE
SLOT_TABLE_OFFSET = 0x424A5
SLOT_COUNT = 55

# Proposed v1 package overhead. Redirect pointers are written in-place in the
# original event stream, so the package itself needs no per-source lookup table.
PACKAGE_HEADER_BYTES = 32
GLYPH_BYTES = 32


def load_rows():
    grouped = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            ko = row["번역"].strip()
            if not ko:
                continue
            grouped[row["영역"]].append({
                "offset": int(row["키(ISO오프셋)"], 16),
                "ko": ko,
                "dup": row["중복그룹"].strip(),
            })
    return grouped


def load_slot_counts():
    with open(ISO_PATH, "rb") as f:
        f.seek(SLOT_TABLE_OFFSET)
        table = f.read(SLOT_COUNT * 4)
    if len(table) != SLOT_COUNT * 4:
        raise ValueError("slot table is truncated")
    return [table[i * 4 + 3] for i in range(SLOT_COUNT)]


def main():
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        global_char_map = json.load(f)

    rows_by_region = load_rows()
    slot_counts = load_slot_counts()
    report = []

    for slot in range(SLOT_COUNT):
        region = f"slot{slot:02d}"
        rows = rows_by_region.get(region, [])

        unique_strings = {}
        glyphs = set()
        for row in rows:
            # Never share storage across independently loaded regions.  Feeding
            # every row into the per-region byte set still deduplicates aliases
            # whose encoded translation is identical inside this slot.
            encoded = encode_string(row["ko"], global_char_map) + b"\x00"
            unique_strings.setdefault(encoded, row["ko"])
            glyphs.update(ch for ch in row["ko"] if ch in global_char_map)

        string_bytes = sum(len(s) for s in unique_strings)
        glyph_bytes = len(glyphs) * GLYPH_BYTES
        package_bytes = 0 if not rows else PACKAGE_HEADER_BYTES + string_bytes + glyph_bytes
        original_bytes = slot_counts[slot] * SECTOR_SIZE
        total_bytes = original_bytes + package_bytes
        needed_sectors = math.ceil(total_bytes / SECTOR_SIZE)
        strings_only_bytes = 0 if not rows else PACKAGE_HEADER_BYTES + string_bytes
        strings_only_sectors = math.ceil((original_bytes + strings_only_bytes) / SECTOR_SIZE)
        free_bytes = SLOT_BYTES - original_bytes
        margin_bytes = SLOT_BYTES - total_bytes

        report.append({
            "slot": f"{slot:02d}",
            "original_sectors": slot_counts[slot],
            "rows": len(rows),
            "unique_strings": len(unique_strings),
            "string_bytes": string_bytes,
            "unique_glyphs": len(glyphs),
            "glyph_bytes": glyph_bytes,
            "header_bytes": PACKAGE_HEADER_BYTES if rows else 0,
            "package_bytes": package_bytes,
            "free_bytes": free_bytes,
            "needed_sectors": needed_sectors,
            "strings_only_sectors": strings_only_sectors,
            "margin_bytes": margin_bytes,
            "status": "FIT" if needed_sectors <= SLOT_SECTORS else "OVERFLOW",
            "strings_status": "FIT" if strings_only_sectors <= SLOT_SECTORS else "OVERFLOW",
        })

    fields = list(report[0])
    with open(REPORT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(report)

    print("Per-slot package feasibility (strings + local 32-byte glyphs)")
    print("slot orig rows uniq_str str_B glyphs glyph_B strNeed allNeed margin strStatus allStatus")
    for r in report:
        if r["rows"] or r["status"] == "OVERFLOW":
            print(
                f'{r["slot"]:>4} {r["original_sectors"]:>4} {r["rows"]:>4} '
                f'{r["unique_strings"]:>8} {r["string_bytes"]:>5} '
                f'{r["unique_glyphs"]:>6} {r["glyph_bytes"]:>7} '
                f'{r["strings_only_sectors"]:>7} {r["needed_sectors"]:>7} '
                f'{r["margin_bytes"]:>7} {r["strings_status"]:>9} {r["status"]}'
            )

    overflow = [r for r in report if r["status"] == "OVERFLOW"]
    string_overflow = [r for r in report if r["strings_status"] == "OVERFLOW"]
    non_slot = {k: len(v) for k, v in rows_by_region.items() if not k.startswith("slot")}
    print(f"\nreport: {REPORT_PATH}")
    print(f"overflow slots: {', '.join(r['slot'] for r in overflow) or 'none'}")
    print(f"string-only overflow slots: {', '.join(r['slot'] for r in string_overflow) or 'none'}")
    print("non-slot regions (handled by module packages later):", non_slot)
    return 1 if overflow else 0


if __name__ == "__main__":
    raise SystemExit(main())
