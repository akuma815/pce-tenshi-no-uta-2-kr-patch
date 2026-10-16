# -*- coding: utf-8 -*-
"""Verify full_extraction CSV integrity against the original Track02 ISO."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
OUT = ROOT / "translation" / "full_extraction"


def load(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    data = ISO.read_bytes()
    master = load(OUT / "master_text.csv")
    batches = []
    batch_sizes = []
    for path in sorted((OUT / "batches_500").glob("*.csv")):
        rows = load(path)
        batches.extend(rows)
        batch_sizes.append(len(rows))

    errors: list[str] = []
    ids = [row["id"] for row in master]
    id_set = set(ids)
    if len(ids) != len(id_set):
        errors.append("master IDs are not unique")
    if [row["id"] for row in batches] != ids:
        errors.append("500-row batches do not reassemble to master order")
    if any(size != 500 for size in batch_sizes[:-1]):
        errors.append("a non-final batch is not exactly 500 rows")
    if batch_sizes and not 1 <= batch_sizes[-1] <= 500:
        errors.append("final batch size is outside 1..500")

    previous = -1
    seen: set[str] = set()
    for row in master:
        offset = int(row["iso_offset"], 16)
        raw = bytes.fromhex(row["raw_hex"])
        if offset < previous:
            errors.append(f"ISO order regression at {row['id']}")
        previous = offset
        if not raw or raw[-1] != 0:
            errors.append(f"record is not 00-terminated: {row['id']}")
        if data[offset:offset + len(raw)] != raw:
            errors.append(f"raw bytes mismatch original ISO: {row['id']}")
        duplicate = row["duplicate_of"]
        if duplicate and duplicate not in seen:
            errors.append(f"duplicate points outside/prior to master: {row['id']} -> {duplicate}")
        seen.add(row["id"])

    report = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    if report["physical_translation_rows"] != len(master):
        errors.append("coverage report physical row count differs from master")
    if report["batch_count"] != len(batch_sizes):
        errors.append("coverage report batch count differs from files")

    result = {
        "ok": not errors,
        "master_rows": len(master),
        "batch_count": len(batch_sizes),
        "batch_sizes": batch_sizes,
        "raw_byte_matches": len(master) if not any("raw bytes mismatch" in e for e in errors) else None,
        "errors": errors,
    }
    (OUT / "verification_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
