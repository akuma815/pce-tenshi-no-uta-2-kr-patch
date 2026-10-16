# -*- coding: utf-8 -*-
"""Materialize KAPLAN1 symbolic targets using the verified $22D0 area-bank ABI.

No ISO mutation is performed.  Output records are ready for a future patch applier.
"""
from __future__ import annotations

import json
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent.parent
PLAN_PATH = GAME_DIR / "translation" / "area_patch_plan.json"
OUT_PATH = GAME_DIR / "translation" / "area_patch_plan_materialized.json"

BANK_SIZE = 8192
LOGICAL_BASE = 0x6000
MAX_BANKS = 24
TOKEN_MODE_FLAG = 0x80


def encode_target(area_offset):
    if not 0 <= area_offset < MAX_BANKS * BANK_SIZE:
        raise ValueError(f"area offset outside 192 KiB: {area_offset:#x}")
    bank_index = area_offset // BANK_SIZE
    logical_address = LOGICAL_BASE + area_offset % BANK_SIZE
    return bank_index, logical_address


def main():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if plan["format"] != "KAPLAN1":
        raise ValueError("unexpected input format")

    redirect_records = []
    continuation_records = []
    load_count_updates = []
    for area in plan["areas"]:
        grid = area["physical_grid"]
        token_mode = bool(area["token_dictionary"])
        for source_hex, target in area["redirects"].items():
            bank_index, address = encode_target(target["area_relative_target"])
            encoded_bank = bank_index | (TOKEN_MODE_FLAG if token_mode else 0)
            record = bytes((0x01, encoded_bank, address & 0xFF, address >> 8, 0x00))
            redirect_records.append({
                "physical_grid": grid,
                "source_iso_offset": int(source_hex, 16),
                "target_area_offset": target["area_relative_target"],
                "bank_index": bank_index,
                "token_mode": token_mode,
                "logical_address": address,
                "record_hex": record.hex(),
            })
        for link in area["continuations"]:
            bank_index, address = encode_target(link["target_area_offset"])
            record = bytes((0x02, bank_index, address & 0xFF, address >> 8))
            continuation_records.append({
                "physical_grid": grid,
                "marker_area_offset": link["marker_area_offset"],
                "target_area_offset": link["target_area_offset"],
                "bank_index": bank_index,
                "logical_address": address,
                "record_hex": record.hex(),
            })
        if area["patched_load_sectors"] != area["original_load_sectors"]:
            for logical_entry in area["logical_entries"]:
                load_count_updates.append({
                    "logical_entry": logical_entry,
                    "physical_grid": grid,
                    "old_sectors": area["original_load_sectors"],
                    "new_sectors": area["patched_load_sectors"],
                })

    # Every source offset and continuation marker must be written exactly once.
    source_offsets = [x["source_iso_offset"] for x in redirect_records]
    if len(source_offsets) != len(set(source_offsets)):
        raise ValueError("duplicate source redirect offsets")
    marker_keys = [(x["physical_grid"], x["marker_area_offset"])
                   for x in continuation_records]
    if len(marker_keys) != len(set(marker_keys)):
        raise ValueError("duplicate continuation marker offsets")
    logical_entries = [x["logical_entry"] for x in load_count_updates]
    if len(logical_entries) != len(set(logical_entries)):
        raise ValueError("duplicate logical load-count updates")

    output = {
        "format": "KAPLAN1-MATERIALIZED",
        "version": 1,
        "runtime_base_bank_variable": "0x22D0",
        "target_formula": "physical=$22D0+bank_index; logical=$6000+(offset%8192)",
        "redirect_bank_flags": {"0x80": "enable Grid15 token expansion"},
        "area_writes": [
            {"physical_grid": area["physical_grid"], "lba": area["lba"],
             "writes": area["writes"], "token_dictionary": area["token_dictionary"]}
            for area in plan["areas"]
        ],
        "redirect_records": redirect_records,
        "continuation_records": continuation_records,
        "load_count_updates": load_count_updates,
    }
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("materialized fetch records:")
    print("  redirects:", len(redirect_records))
    print("  continuations:", len(continuation_records))
    print("  logical load-count updates:", len(load_count_updates))
    print("output:", OUT_PATH)


if __name__ == "__main__":
    main()
