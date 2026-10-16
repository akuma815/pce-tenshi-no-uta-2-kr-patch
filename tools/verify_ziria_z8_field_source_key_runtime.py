#!/usr/bin/env python3
"""Independently verify the immutable Z8.4 runtime source-key result."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z8_field_source_key_runtime_manifest.json"
BANK_BASE = 0x68


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest["status"] == "RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN",
        "manifest status",
    )
    for item in manifest["inputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"missing input: {path}")
        require(sha256(path) == item["sha256"], f"input hash: {path}")

    trace = rows(ROOT / manifest["inputs"]["runtime_trace"]["path"])
    lookup_rows = rows(ROOT / manifest["inputs"]["lookup"]["path"])
    lookup = {row["source_key"]: row for row in lookup_rows}
    probe = json.loads(
        (ROOT / manifest["inputs"]["probe_manifest"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    require(len(lookup_rows) == len(lookup) == 236, "lookup denominator")
    require(len(trace) == manifest["trace"]["rows"] == 852, "trace rows")

    hits = [row for row in trace if row["event"] == "START_HIT"]
    require(len(hits) == manifest["trace"]["start_hits"] == 9, "start hits")
    ids = sorted({row["catalog_id"] for row in hits})
    require(ids == manifest["trace"]["unique_start_hit_ids"], "manifest hit IDs")
    require(ids == sorted(probe["offline_replay"]["exact_start_ids"]), "offline IDs")
    for row in hits:
        logical = int(row["logical"], 16)
        mpr = int(row["mpr"], 16)
        key = f"{(mpr - BANK_BASE) * 0x2000 + (logical & 0x1FFF):06X}"
        require(row["source_key"] == key, f"source key: {row['frame']}")
        item = lookup[key]
        require(item["id"] == row["catalog_id"], f"lookup ID: {row['frame']}")
        require(
            item["source_iso_offset"] == row["catalog_iso_offset"],
            f"lookup ISO: {row['frame']}",
        )
        require(
            row["scene_identity_source"] == "observed_mode06_cd_read",
            f"scene identity: {row['frame']}",
        )

    transitions = manifest["trace"]["cd_transitions"]
    require(transitions[0]["lba"] == 482, "field LBA")
    require([item["lba"] for item in transitions] == [482, 290, 2882], "LBA transitions")
    require(manifest["runtime_gate"]["status"] == "PASS", "runtime gate")
    require(manifest["redirect_index"]["status"] == "NOT_BUILT", "redirect gate")
    print(
        json.dumps(
            {
                "status": "PASS",
                "trace_rows": len(trace),
                "start_hits": len(hits),
                "unique_start_hits": len(ids),
                "source_key_mismatches": 0,
                "lookup_mismatches": 0,
                "redirect_index_built": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
