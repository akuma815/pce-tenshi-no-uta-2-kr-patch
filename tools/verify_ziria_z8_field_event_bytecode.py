#!/usr/bin/env python3
"""Independent fail-closed verifier for the Z8.5 static reference outputs."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
CATALOG = ROOT / "module_relink" / "z8_field_event_refs" / "field_event_reference_catalog.csv"
MANIFEST = ROOT / "translation" / "ziria_z8_field_event_bytecode_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_5_field_event_bytecode_result.md"
MODULE_START = 482 * 2048


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with CATALOG.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    image = ISO.read_bytes()

    if manifest["status"] != "STATIC_DENOMINATOR_PASS_BOUNDARY_REPAIR_REQUIRED":
        raise ValueError("unexpected status")
    if len(rows) != 236 or manifest["population"]["structural_text_consumers"] != 235:
        raise ValueError("population mismatch")
    if sha256(CATALOG) != manifest["outputs"]["catalog_sha256"]:
        raise ValueError("catalog hash mismatch")
    if not REPORT.is_file():
        raise FileNotFoundError(REPORT)

    kinds = Counter(row["reference_kind"] for row in rows)
    boundaries = Counter(row["boundary_status"] for row in rows)
    if kinds != Counter({
        "INLINE_OPCODE_02": 217,
        "INLINE_OPCODE_03": 10,
        "INLINE_OPCODE_14": 1,
        "MEMO_POINTER_TABLE": 7,
        "FALSE_POSITIVE_KANA_TABLE": 1,
    }):
        raise ValueError(f"kind counts changed: {kinds}")
    if boundaries != Counter({
        "EXACT": 232,
        "MASTER_PREFIX_UNDERREAD": 2,
        "MASTER_PREFIX_OVERREAD": 1,
        "EXCLUDE": 1,
    }):
        raise ValueError(f"boundary counts changed: {boundaries}")

    memo_targets = []
    for row in rows:
        kind = row["reference_kind"]
        if kind.startswith("INLINE_OPCODE_"):
            opcode = int(kind[-2:], 16)
            storage = int(row["reference_storage_iso_offset"], 16)
            target = int(row["structural_source_iso_offset"], 16)
            if storage + 1 != target or image[storage] != opcode:
                raise ValueError(f"inline owner mismatch: {row['id']}")
        elif kind == "MEMO_POINTER_TABLE":
            storage = int(row["reference_storage_iso_offset"], 16)
            target = int(row["structural_source_iso_offset"], 16)
            logical = int.from_bytes(image[storage:storage + 2], "little")
            resolved = MODULE_START + 0x2E000 + logical - 0xC000
            if target != resolved:
                raise ValueError(f"Memo pointer mismatch: {row['id']}")
            memo_targets.append(target)
        elif kind == "FALSE_POSITIVE_KANA_TABLE":
            if row["redirect_eligible"] != "no" or row["structural_source_iso_offset"]:
                raise ValueError("false positive was not excluded")

        if row["boundary_status"] != "EXACT" and row["redirect_eligible"] != "no":
            raise ValueError(f"unsafe row marked eligible: {row['id']}")

    if memo_targets != [0x011F01E, 0x011F029, 0x011F031, 0x011F03B,
                        0x011F043, 0x011F04F, 0x011F059]:
        raise ValueError("Memo target sequence changed")

    print("Z8.5 FIELD EVENT BYTECODE: PASS "
          "(235 consumers, 232 exact, 3 repairs, 1 excluded)")


if __name__ == "__main__":
    main()
