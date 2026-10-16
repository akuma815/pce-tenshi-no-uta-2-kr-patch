# -*- coding: utf-8 -*-
"""Capacity audit for only the physical area grids referenced by $54A5."""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tools"))
from patch_iso import encode_string

TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
TOPOLOGY_PATH = os.path.join(GAME_DIR, "translation", "slot_topology.json")
REPORT_PATH = os.path.join(GAME_DIR, "translation", "mapped_area_package_report.tsv")

SECTOR_SIZE = 2048
BANK_SIZE = 8192
MAX_SECTORS = 96
HEADER_SIZE = 32
GLYPH_SIZE = 32


def bank_safe_size(chunks, start):
    pos = start
    padding = 0
    for chunk in chunks:
        in_bank = pos % BANK_SIZE
        if in_bank + len(chunk) > BANK_SIZE:
            pad = BANK_SIZE - in_bank
            pos += pad
            padding += pad
        pos += len(chunk)
    return pos - start, padding


def main():
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        topology = json.load(f)
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)

    rows_by_grid = defaultdict(list)
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            region = row["영역"]
            ko = row["번역"].strip()
            if ko and region.startswith("slot"):
                rows_by_grid[int(region[4:6])].append((
                    int(row["키(ISO오프셋)"], 16), ko))

    report = []
    for grid in topology["physical_grids"]:
        if not grid["logical_entries"] or not grid["translated_rows"]:
            continue
        if len(set(grid["load_counts"])) != 1:
            raise ValueError(f"grid{grid['grid']:02d}: inconsistent load counts")
        load_sectors = grid["load_counts"][0]
        live_start = grid["lba"] * SECTOR_SIZE
        live_end = live_start + load_sectors * SECTOR_SIZE
        texts = [text for source, text in rows_by_grid[grid["grid"]]
                 if live_start <= source < live_end]
        if not texts:
            continue
        unique_strings = {encode_string(t, char_map) + b"\x00" for t in texts}
        glyphs = {ch for t in texts for ch in t if ch in char_map}

        package_start = load_sectors * SECTOR_SIZE
        string_chunks = sorted(unique_strings, key=len, reverse=True)
        string_storage, string_padding = bank_safe_size(
            string_chunks, package_start + HEADER_SIZE)
        string_package = HEADER_SIZE + string_storage
        string_end = package_start + string_package
        glyph_chunks = [b"\x00" * GLYPH_SIZE for _ in glyphs]
        glyph_storage, glyph_padding = bank_safe_size(glyph_chunks, string_end)
        all_package = string_package + glyph_storage

        string_need = math.ceil((package_start + string_package) / SECTOR_SIZE)
        all_need = math.ceil((package_start + all_package) / SECTOR_SIZE)
        report.append({
            "physical_grid": f'{grid["grid"]:02d}',
            "lba": grid["lba"],
            "logical_entries": ",".join(map(str, grid["logical_entries"])),
            "load_sectors": load_sectors,
            "rows": len(texts),
            "unique_strings": len(unique_strings),
            "string_bytes": sum(map(len, unique_strings)),
            "string_bank_padding": string_padding,
            "string_package_bytes": string_package,
            "string_needed_sectors": string_need,
            "unique_glyphs": len(glyphs),
            "glyph_bytes": len(glyphs) * GLYPH_SIZE,
            "glyph_bank_padding": glyph_padding,
            "all_needed_sectors": all_need,
            "string_status": "FIT" if string_need <= MAX_SECTORS else "OVERFLOW",
            "all_status": "FIT" if all_need <= MAX_SECTORS else "OVERFLOW",
        })

    fields = list(report[0])
    with open(REPORT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(report)

    print("grid LBA load logical rows strings strNeed glyphs allNeed strStatus allStatus")
    for r in report:
        print(f'{r["physical_grid"]:>4} {r["lba"]:>4} {r["load_sectors"]:>4} '
              f'{r["logical_entries"]:>15} {r["rows"]:>4} {r["unique_strings"]:>7} '
              f'{r["string_needed_sectors"]:>7} {r["unique_glyphs"]:>6} '
              f'{r["all_needed_sectors"]:>7} {r["string_status"]:>9} {r["all_status"]}')
    string_over = [r["physical_grid"] for r in report if r["string_status"] == "OVERFLOW"]
    all_over = [r["physical_grid"] for r in report if r["all_status"] == "OVERFLOW"]
    print(f"\ntranslated mapped grids: {len(report)}")
    print("string overflow:", ", ".join(string_over) or "none")
    print("string+glyph overflow:", ", ".join(all_over) or "none")
    print("report:", REPORT_PATH)
    return 1 if string_over else 0


if __name__ == "__main__":
    raise SystemExit(main())
