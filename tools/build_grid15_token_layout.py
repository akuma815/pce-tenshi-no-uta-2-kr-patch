# -*- coding: utf-8 -*-
"""Build and verify the Grid15 one-byte glyph-token + continuation layout."""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GAME_DIR, "tools"))
from patch_iso import encode_string
from pack_fragmented_area_chains import allocate_chain, merge_ranges, split_banks

ISO_PATH = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
TSV_PATH = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
CHAR_MAP_PATH = os.path.join(GAME_DIR, "translation", "char_map.json")
TOPOLOGY_PATH = os.path.join(GAME_DIR, "translation", "slot_topology.json")
OUT_PATH = os.path.join(GAME_DIR, "translation", "fragmented_area_chains", "grid15_token_chains.json")

GRID = 15
SECTOR_SIZE = 2048
BANK_SIZE = 8192
AREA_BYTES = 96 * SECTOR_SIZE
REDIRECT_SIZE = 5
TOKEN_BYTES = list(range(0x03, 0x0B)) + list(range(0x0F, 0x20))


def choose_dictionary(strings):
    counts = Counter()
    for data in strings:
        for i in range(len(data) - 1):
            # Korean custom codes currently occupy lead bytes EB..EF.
            if 0xEB <= data[i] <= 0xEF:
                counts[data[i:i + 2]] += 1
    chosen = counts.most_common(len(TOKEN_BYTES))
    return {token: sequence for token, (sequence, _) in zip(TOKEN_BYTES, chosen)}


def compress(data, dictionary):
    reverse = {sequence: token for token, sequence in dictionary.items()}
    out = bytearray()
    i = 0
    while i < len(data):
        token = reverse.get(data[i:i + 2])
        if token is not None:
            out.append(token)
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def decompress(data, dictionary):
    out = bytearray()
    for value in data:
        sequence = dictionary.get(value)
        if sequence is None:
            out.append(value)
        else:
            out.extend(sequence)
    return bytes(out)


def main():
    iso = open(ISO_PATH, "rb").read()
    with open(CHAR_MAP_PATH, encoding="utf-8") as f:
        char_map = json.load(f)
    with open(TOPOLOGY_PATH, encoding="utf-8") as f:
        topology = json.load(f)
    grid = next(x for x in topology["physical_grids"] if x["grid"] == GRID)
    area_start = grid["lba"] * SECTOR_SIZE
    live_end = area_start + grid["load_counts"][0] * SECTOR_SIZE
    load_sectors = grid["load_counts"][0]

    rows = []
    with open(TSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["영역"] == "slot15" and row["번역"].strip():
                rows.append((int(row["키(ISO오프셋)"], 16),
                             encode_string(row["번역"].strip(), char_map) + b"\x00"))
    rows = [row for row in rows if area_start <= row[0] < live_end]

    originals = set(data for _, data in rows)
    dictionary = choose_dictionary(originals)
    if len(dictionary) != len(TOKEN_BYTES):
        raise ValueError("not enough token candidates")
    compressed = {data: compress(data, dictionary) for data in originals}
    for original, packed in compressed.items():
        if decompress(packed, dictionary) != original:
            raise AssertionError("token round-trip failed")

    holes = [[load_sectors * SECTOR_SIZE, AREA_BYTES]]
    for source_offset, _ in rows:
        end = iso.find(b"\x00", source_offset, min(len(iso), source_offset + SECTOR_SIZE)) + 1
        if end <= source_offset:
            raise ValueError(f"unterminated source at {source_offset:#x}")
        start = source_offset - area_start
        stop = end - area_start
        if not (0 <= start < stop <= AREA_BYTES):
            raise ValueError(f"source outside Grid15 at {source_offset:#x}")
        holes.append([start + REDIRECT_SIZE, stop])
    free_ranges = split_banks(merge_ranges(holes))
    initial_free = sum(b - a for a, b in free_ranges)

    chains = {}
    for original in sorted(originals, key=lambda x: len(compressed[x]), reverse=True):
        packed = compressed[original]
        chain = allocate_chain(free_ranges, packed)
        if chain is None:
            raise ValueError(f"compressed Grid15 still does not fit; remaining={sum(b-a for a,b in free_ranges)}")
        chains[original] = chain

    token_savings = sum(len(x) - len(compressed[x]) for x in originals)
    total_markers = sum(len(chain) - 1 for chain in chains.values())
    layout = {
        "format": "KAT1",
        "physical_grid": GRID,
        "lba": grid["lba"],
        "logical_entries": grid["logical_entries"],
        "original_load_sectors": load_sectors,
        "extended_load_sectors": 96,
        "token_dictionary": {f"{token:02x}": sequence.hex() for token, sequence in dictionary.items()},
        "dictionary_code_bytes": len(dictionary) * 2,
        "uncompressed_unique_bytes": sum(map(len, originals)),
        "compressed_unique_bytes": sum(len(compressed[x]) for x in originals),
        "token_savings_bytes": token_savings,
        "initial_free_bytes": initial_free,
        "remaining_free_bytes": sum(b - a for a, b in free_ranges),
        "continuation_markers": total_markers,
        "chains": [
            {
                "original_data_hex": original.hex(),
                "compressed_data_hex": compressed[original].hex(),
                "segments": [
                    {"area_relative_offset": s["offset"], "data_hex": s["data"].hex(),
                     "data_length": len(s["data"]), "final": s["final"]}
                    for s in chain
                ],
            }
            for original, chain in chains.items()
        ],
        "redirects": {
            f"{source_offset:07x}": {"area_relative_target": chains[original][0]["offset"]}
            for source_offset, original in rows
        },
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)

    print(f"Grid15 token layout OK: {len(originals)} unique / {len(rows)} sources")
    print(f"tokens: {len(dictionary)}, dictionary code table: {len(dictionary) * 2} B")
    print(f"unique bytes: {layout['uncompressed_unique_bytes']} -> {layout['compressed_unique_bytes']} "
          f"(saved {token_savings} B)")
    print(f"continuation markers: {total_markers}")
    print(f"free bytes: {initial_free} -> {layout['remaining_free_bytes']}")
    print("output:", OUT_PATH)


if __name__ == "__main__":
    main()
