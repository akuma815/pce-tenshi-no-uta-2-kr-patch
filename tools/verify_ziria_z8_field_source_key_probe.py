#!/usr/bin/env python3
"""Independently verify Z8.3 source-key probe inputs and offline replay."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z8_field_source_key_probe_manifest.json"
BANK_BASE = 0x68


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def rows(path: Path, delimiter: str = "\t") -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=delimiter))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest["status"] == "OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING",
        "manifest status",
    )
    for item in manifest["inputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"missing input: {path}")
        require(sha256(path) == item["sha256"], f"input hash: {path}")
    for name in ("lookup", "offline_replay"):
        item = manifest[name]
        path = ROOT / item["path"]
        require(path.is_file(), f"missing output: {path}")
        require(sha256(path) == item["sha256"], f"output hash: {path}")

    reference_manifest = json.loads(
        (ROOT / manifest["inputs"]["reference_manifest"]["path"]).read_text(encoding="utf-8")
    )
    catalog_path = ROOT / manifest["inputs"]["reference_catalog"]["path"]
    catalog = rows(catalog_path, ",")
    catalog_by_id = {row["id"]: row for row in catalog}
    lookup = rows(ROOT / manifest["lookup"]["path"])
    require(len(lookup) == manifest["lookup"]["rows"] == 236, "lookup population")
    require(len({row["source_key"] for row in lookup}) == 236, "lookup key uniqueness")
    require(len({row["id"] for row in lookup}) == 236, "lookup ID uniqueness")
    for row in lookup:
        require(row["id"] in catalog_by_id, f"lookup ID: {row['id']}")
        catalog_row = catalog_by_id[row["id"]]
        relative = int(catalog_row["source_module_offset"], 16)
        require(row["source_key"] == f"{relative:06X}", f"lookup key: {row['id']}")
        require(row["source_iso_offset"] == catalog_row["source_iso_offset"], f"lookup ISO: {row['id']}")
        require(row["raw_length"] == catalog_row["raw_length"], f"lookup length: {row['id']}")

    replay = rows(ROOT / manifest["offline_replay"]["path"])
    replay_meta = manifest["offline_replay"]
    require(len(replay) == replay_meta["scene_stream_rows"] == 828, "replay population")
    exact_ids = set()
    containing_ids = set()
    for row in replay:
        logical = int(row["logical"], 16)
        mpr = int(row["mpr"], 16)
        require(BANK_BASE <= mpr <= 0x7F, "replay bank")
        expected = (mpr - BANK_BASE) * 0x2000 + (logical & 0x1FFF)
        require(row["source_key"] == f"{expected:06X}", "replay key formula")
        require(row["key_matches_trace_overlay"] == "yes", "replay overlay mismatch")
        require(row["key_matches_trace_iso"] == "yes", "replay ISO mismatch")
        if row["catalog_id"] != "-":
            exact_ids.add(row["catalog_id"])
        if row["containing_record_id"] != "-":
            containing_ids.add(row["containing_record_id"])
    require(len(exact_ids) == replay_meta["unique_exact_start_hits"] == 8, "exact hit count")
    require(len(containing_ids) == replay_meta["unique_containing_record_hits"] == 9, "containing hit count")
    require(replay_meta["key_mismatches"] == 0, "key mismatch metadata")
    require(replay_meta["iso_mismatches"] == 0, "ISO mismatch metadata")

    lua_path = ROOT / manifest["inputs"]["lua_probe"]["path"]
    lua = lua_path.read_text(encoding="utf-8")
    for forbidden in (
        "memory.write", "mainmemory.write", "joypad.set", "savestate.load",
        "emu.setregister", "client.openrom", "event.on_bus_write",
    ):
        require(forbidden not in lua, f"write-capable Lua API: {forbidden}")
    for hook in ("0x4293", "0x42DE", "0x42AB", "0x42BA", "0xE009"):
        require(hook in lua, f"missing Lua hook: {hook}")
    require("lookup_count == 236" in lua, "Lua lookup denominator assertion")
    require(manifest["runtime_gate"]["status"] == "PENDING", "runtime gate")
    require(
        reference_manifest["redirect_index"]["status"] == "NOT_BUILT",
        "redirect must remain blocked",
    )

    print(json.dumps({
        "status": "PASS",
        "lookup_rows": len(lookup),
        "offline_replay_rows": len(replay),
        "unique_exact_start_hits": len(exact_ids),
        "unique_containing_record_hits": len(containing_ids),
        "write_capable_lua_apis": 0,
        "runtime_capture": "PENDING",
        "redirect_index_built": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
