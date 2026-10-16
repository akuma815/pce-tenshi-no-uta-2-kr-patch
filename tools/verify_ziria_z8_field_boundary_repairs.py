#!/usr/bin/env python3
"""Independent fail-closed verifier for the Z8.6 repair overlay and index."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
EVENT_CATALOG = (
    ROOT / "module_relink" / "z8_field_event_refs"
    / "field_event_reference_catalog.csv"
)
REPAIR_CSV = ROOT / "translation" / "ziria_z8_field_boundary_repairs.csv"
INDEX_TSV = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
MANIFEST = ROOT / "translation" / "ziria_z8_field_boundary_repair_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_6_field_boundary_repair_result.md"
BUILDER = ROOT / "tools" / "build_ziria_z8_field_boundary_repairs.py"
MODULE_START = 482 * 2048


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    encoding = "utf-8-sig" if delimiter == "," else "utf-8"
    with path.open("r", encoding=encoding, newline="") as source:
        return list(csv.DictReader(source, delimiter=delimiter))


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repairs = read_csv(REPAIR_CSV)
    index = read_csv(INDEX_TSV, "\t")
    events = read_csv(EVENT_CATALOG)
    image = ISO.read_bytes()

    if manifest["status"] != "BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED":
        raise ValueError("unexpected Z8.6 status")
    if len(events) != 236 or len(repairs) != 4 or len(index) != 235:
        raise ValueError("population mismatch")
    if not REPORT.is_file():
        raise FileNotFoundError(REPORT)
    if sha256(MASTER) != manifest["inputs"]["master_text"]["sha256"]:
        raise ValueError("immutable master hash mismatch")
    if sha256(EVENT_CATALOG) != manifest["inputs"]["event_catalog"]["sha256"]:
        raise ValueError("event catalog hash mismatch")
    if sha256(REPAIR_CSV) != manifest["outputs"]["repair_overlay_sha256"]:
        raise ValueError("repair overlay hash mismatch")
    if sha256(INDEX_TSV) != manifest["outputs"]["source_key_index_sha256"]:
        raise ValueError("source-key index hash mismatch")

    actions = Counter(row["repair_action"] for row in repairs)
    if actions != Counter({
        "PREFIX_UNDERREAD_REPLACED": 2,
        "POINTER_PREFIX_OVERREAD_REPLACED": 1,
        "EXCLUDED_FALSE_POSITIVE": 1,
    }):
        raise ValueError(f"repair action population changed: {actions}")
    corrected = {
        row["legacy_id"]: row["corrected_id"] for row in repairs
        if row["corrected_id"]
    }
    if corrected != {
        "iso:010CAE1": "iso:010CABD",
        "iso:010D080": "iso:010D036",
        "iso:011F011": "iso:011F01E",
    }:
        raise ValueError(f"corrected ID set changed: {corrected}")

    ids: set[str] = set()
    keys: set[str] = set()
    boundaries: Counter[str] = Counter()
    for row in index:
        source = int(row["source_iso_offset"], 16)
        module_offset = source - MODULE_START
        key = bytes.fromhex(row["source_key_u24le"])
        if len(key) != 3 or int.from_bytes(key, "little") != module_offset:
            raise ValueError(f"source-key mismatch: {row['id']}")
        physical = 0x68 + module_offset // 0x2000
        if int(row["source_physical_bank"], 16) != physical:
            raise ValueError(f"physical-bank mismatch: {row['id']}")
        if int(row["source_bank_offset"], 16) != module_offset & 0x1FFF:
            raise ValueError(f"bank-offset mismatch: {row['id']}")
        raw = bytes.fromhex(row["raw_hex"])
        if len(raw) != int(row["raw_length"]) or raw[-1] != 0:
            raise ValueError(f"raw shape mismatch: {row['id']}")
        if b"\0" in raw[:-1] or image[source:source + len(raw)] != raw:
            raise ValueError(f"raw ISO mismatch: {row['id']}")
        if hashlib.sha256(raw).hexdigest().upper() != row["raw_sha256"]:
            raise ValueError(f"raw hash mismatch: {row['id']}")
        ids.add(row["id"])
        keys.add(row["source_key_u24le"])
        boundaries[row["boundary_status"]] += 1

    if len(ids) != 235 or len(keys) != 235:
        raise ValueError("corrected ID/source-key uniqueness failed")
    if boundaries != Counter({"EXACT": 232, "REPAIRED": 3}):
        raise ValueError(f"boundary population changed: {boundaries}")
    if "iso:010F080" in {row["legacy_id"] for row in index}:
        raise ValueError("false positive remains in corrected index")

    before = (sha256(REPAIR_CSV), sha256(INDEX_TSV))
    subprocess.run([sys.executable, str(BUILDER)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    after = (sha256(REPAIR_CSV), sha256(INDEX_TSV))
    if before != after:
        raise ValueError("builder output is not deterministic")

    print("Z8.6 FIELD BOUNDARY REPAIR: PASS "
          "(235 consumers, 232 exact, 3 repaired, 1 excluded)")


if __name__ == "__main__":
    main()
