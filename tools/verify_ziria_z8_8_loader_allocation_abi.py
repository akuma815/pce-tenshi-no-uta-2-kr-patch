#!/usr/bin/env python3
"""Independent verifier for the read-only Z8.8 gate."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z8_8_loader_allocation_abi_manifest.json"
RANGES = ROOT / "module_relink" / "z8_8_loader_allocation_abi" / "source_reclaim_ranges.tsv"
ENGINE = ROOT / "module_relink" / "track02" / "semantic_modules" / "field.main_engine_lba0258_s20.bin"


def main() -> None:
	m = json.loads(MANIFEST.read_text(encoding="utf-8"))
	if m["status"] != "ABI_PASS_UNCHANGED_WIRE_ALLOCATION_FAIL":
		raise SystemExit("unexpected Z8.8 status")
	if m["mutation_scope"] != "analysis-only; no CUE/BIN/ISO or emulated-state writes":
		raise SystemExit("mutation scope changed")

	storage = m["loader_owned_storage"]
	if storage["covered_bank_count"] != 32 or storage["free_persistent_bank_count"] != 0:
		raise SystemExit("resident bank ownership proof failed")
	if storage["approved_extension_allocations"] != 0:
		raise SystemExit("extension registry is no longer empty")
	if storage["unchanged_wire_all_assets_fit"]:
		raise SystemExit("unchanged wire unexpectedly fits")
	for name, item in storage["unchanged_wire_asset_fit"].items():
		if item["fits_unchanged_wire"]:
			raise SystemExit(f"{name} unexpectedly fits one reclaim run")

	with RANGES.open(encoding="utf-8", newline="") as source:
		rows = list(csv.DictReader(source, delimiter="\t"))
	if len(rows) != 235:
		raise SystemExit("reclaim denominator changed")
	ranges = []
	for row in rows:
		start = int(row["scene_offset"], 16)
		end = int(row["end_exclusive"], 16)
		if end - start != int(row["bytes"]):
			raise SystemExit("range length mismatch")
		ranges.append((start, end))
	for left, right in zip(sorted(ranges), sorted(ranges)[1:]):
		if left[1] > right[0]:
			raise SystemExit("source reclaim ranges overlap")
	if sum(end - start for start, end in ranges) != storage["source_reclaim"]["bytes"]:
		raise SystemExit("reclaim total mismatch")

	engine = ENGINE.read_bytes()
	reader = engine[0x284:0x2F0]
	if hashlib.sha256(reader).hexdigest().upper() != m["reader_abi"]["reader_sha256"]:
		raise SystemExit("reader bytes changed")
	if engine[0x36:0x39] != b"\x4C\x84\x42":
		raise SystemExit("$4036 no longer jumps to $4284")
	if sum(engine[i:i + 3] == b"\x20\x36\x40" for i in range(len(engine) - 2)) != m["reader_abi"]["direct_jsr_4036_count_in_engine"]:
		raise SystemExit("reader callsite count changed")
	required = [
		b"\xA5\x55\xD0",  # LDA $55 / BNE
		b"\xA5\x53\xD0",  # LDA $53 / BNE
		b"\xAD\x69\x2E\xD0",  # LDA $2E69 / BNE
		b"\xB2\x4B", b"\xB2\x52", b"\xB2\x54",
		b"\x64\x54\x64\x55\x4C\x84\x42",
	]
	if any(signature not in reader for signature in required):
		raise SystemExit("reader ABI signature missing")
	if m["gate"] != {
		"abi": "PASS",
		"loader_owned_allocation_for_unchanged_z8_7_wire": "FAIL",
		"disc_build": "BLOCKED",
		"reason": "no approved persistent bank and no reclaim run can hold any required contiguous wire blob",
	}:
		raise SystemExit("gate decision changed")
	print("PASS: Z8.8 ABI is closed and unchanged Z8.7 allocation is correctly blocked")


if __name__ == "__main__":
	main()
