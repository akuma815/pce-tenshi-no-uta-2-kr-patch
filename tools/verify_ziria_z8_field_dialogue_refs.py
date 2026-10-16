#!/usr/bin/env python3
"""Verify the Z8.2 field-dialogue reference catalogue independently."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z8_field_dialogue_reference_manifest.json"
MODULE_START = 482 * 2048
MODULE_END = (482 + 96) * 2048
BANK_BASE = 0x68


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest["status"] == "LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN",
        "manifest status",
    )
    for item in manifest["inputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"missing input: {path}")
        require(sha256(path) == item["sha256"], f"input hash: {path}")
    for name in ("reference_catalog", "observed_starts", "loader_reference"):
        path = ROOT / manifest["outputs"][name]
        require(path.is_file(), f"missing output: {path}")
        require(
            sha256(path) == manifest["outputs"][f"{name}_sha256"],
            f"output hash: {path}",
        )

    iso = (ROOT / manifest["inputs"]["track02_iso"]["path"]).read_bytes()
    loader = json.loads((ROOT / manifest["outputs"]["loader_reference"]).read_text(encoding="utf-8"))
    storage = loader["storage_coordinate"]
    target = loader["target_coordinate"]
    storage_offset = int(storage["track02_iso_offset"], 16)
    raw = bytes.fromhex(storage["raw_hex"])
    require(iso[storage_offset:storage_offset + 4] == raw, "loader raw")
    require(int.from_bytes(raw[:3], "big") == 482 and raw[3] == 96, "loader decode")
    require(int(target["track02_iso_start"], 16) == MODULE_START, "module start")
    require(int(target["track02_iso_end_exclusive"], 16) == MODULE_END, "module end")
    require(loader["denominator"]["matching_lba_count_entries"] == 1, "loader denominator")

    catalog = read_csv(ROOT / manifest["outputs"]["reference_catalog"])
    require(len(catalog) == 236, "catalogue count")
    require(len({row["id"] for row in catalog}) == 236, "catalogue stable IDs")
    require(
        [int(row["source_iso_offset"], 16) for row in catalog]
        == sorted(int(row["source_iso_offset"], 16) for row in catalog),
        "catalogue order",
    )

    observed = 0
    fully_observed = 0
    for row in catalog:
        source = int(row["source_iso_offset"], 16)
        relative = int(row["source_module_offset"], 16)
        require(source - MODULE_START == relative, f"relative source: {row['id']}")
        require(MODULE_START <= source < MODULE_END, f"source extent: {row['id']}")
        require(
            int.from_bytes(bytes.fromhex(row["source_key_u24le"]), "little") == relative,
            f"source key: {row['id']}",
        )
        physical = int(row["source_physical_bank"], 16)
        bank_offset = int(row["source_bank_offset"], 16)
        require(physical == BANK_BASE + relative // 8192, f"physical bank: {row['id']}")
        require(bank_offset == relative % 8192, f"bank offset: {row['id']}")
        require(BANK_BASE <= physical <= 0x7F, f"bank range: {row['id']}")
        require(row["terminator"] == "00", f"terminator policy: {row['id']}")
        require(row["literal_scan_policy"] == "NOT_REFERENCE_EVIDENCE", f"literal policy: {row['id']}")
        if row["runtime_observed"] == "yes":
            observed += 1
        if row["runtime_fully_observed"] == "yes":
            fully_observed += 1

    population = manifest["text_reference_population"]
    require(observed == population["runtime_observed_records"] == 9, "observed count")
    require(fully_observed == population["runtime_fully_observed_records"] == 8, "full count")
    require(population["runtime_unobserved_records"] == 227, "unobserved count")
    require(manifest["redirect_index"]["status"] == "NOT_BUILT", "redirect must remain blocked")

    output_root = ROOT / "module_relink" / "z8_field_dialogue_refs"
    require(not list(output_root.rglob("*.cue")), "unexpected CUE")
    require(not list(output_root.rglob("*.bin")), "unexpected BIN")

    print(json.dumps({
        "status": "PASS",
        "loader_reference": "PASS",
        "catalogued_records": len(catalog),
        "runtime_observed_records": observed,
        "runtime_unobserved_records": len(catalog) - observed,
        "redirect_index_built": False,
        "disc_mutated": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
