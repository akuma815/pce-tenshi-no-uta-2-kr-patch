#!/usr/bin/env python3
"""Fail-closed verification for the Ziria Z1 catalogue and graph."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "translation" / "ziria_module_catalog.json"
GRAPH = ROOT / "translation" / "ziria_loader_graph.json"
EXPECTED_HASH = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    assert catalog["source"]["sha256"] == EXPECTED_HASH
    assert catalog["source"]["disc_mutated"] is False
    assert catalog["loader"]["overlay_table"]["runtime_address"] == "0x6531"
    assert catalog["loader"]["routine"]["cd_read_callsite_runtime"] == "0x66FC"
    assert catalog["loader"]["routine"]["bios_cd_read_entry"] == "0xE009"

    modules = {item["id"]: item for item in catalog["modules"]}
    expected = {
        "field.main_engine": (258, 20, "0x80-0x84"),
        "scene.field_start": (482, 96, "0x68-0x7F"),
        "scene.battle_first": (290, 96, "0x68-0x7F"),
        "scene.tower_first": (2882, 96, "0x68-0x7F"),
    }
    for module_id, (lba, sectors, banks) in expected.items():
        item = modules[module_id]
        assert item["lba"] == lba
        assert item["sector_count"] == sectors
        assert item["physical_bank_interval"] == banks

    overlay = catalog["directories"]["overlay"]["entries"]
    refs = {lba: [x["logical_entry"] for x in overlay if x["lba"] == lba]
            for lba in (290, 482, 2882)}
    assert refs == {290: [0], 482: [2], 2882: [27]}

    edges = {(x["from"], x["to"], x["type"]) for x in graph["edges"]}
    required_edges = {
        ("scene.field_start", "scene.battle_first", "directory_load"),
        ("scene.battle_first", "scene.field_start", "observed_return_route"),
        ("scene.battle_first", "scene.tower_first", "observed_tower_route"),
        ("scene.field_start", "subrenderer.memo", "resident_call_no_cd_read"),
        ("scene.field_start", "subrenderer.portrait", "resident_call_no_cd_read"),
    }
    assert required_edges <= edges
    assert graph["source_bin_sha256"] == EXPECTED_HASH
    print("PASS: Z1 catalogue and loader graph are internally consistent")
    print(f"modules={len(modules)} edges={len(edges)} overlay_entries={len(overlay)}")


if __name__ == "__main__":
    main()
