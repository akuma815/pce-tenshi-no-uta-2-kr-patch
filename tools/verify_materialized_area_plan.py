#!/usr/bin/env python3
"""Independently verify materialized area fetch records."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "translation" / "area_patch_plan_materialized.json"
SYMBOLIC_PLAN = ROOT / "translation" / "area_patch_plan.json"


def decode_target(record: bytes) -> tuple[int, int]:
	bank_index = record[1] & 0x7F
	logical_address = record[2] | record[3] << 8
	assert bank_index < 24
	assert 0x6000 <= logical_address <= 0x7FFF
	return bank_index, bank_index * 8192 + logical_address - 0x6000


def main() -> None:
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	symbolic = json.loads(SYMBOLIC_PLAN.read_text(encoding="utf-8"))
	assert plan["format"] == "KAPLAN1-MATERIALIZED"

	redirect_sources = set()
	for item in plan["redirect_records"]:
		record = bytes.fromhex(item["record_hex"])
		assert len(record) == 5 and record[0] == 0x01 and record[4] == 0
		bank_index, target = decode_target(record)
		assert bank_index == item["bank_index"]
		assert bool(record[1] & 0x80) == item["token_mode"]
		assert item["token_mode"] == (item["physical_grid"] == 15)
		assert target == item["target_area_offset"]
		key = item["physical_grid"], item["source_iso_offset"]
		assert key not in redirect_sources
		redirect_sources.add(key)

	continuation_markers = set()
	for item in plan["continuation_records"]:
		record = bytes.fromhex(item["record_hex"])
		assert len(record) == 4 and record[0] == 0x02
		bank_index, target = decode_target(record)
		assert not record[1] & 0x80
		assert bank_index == item["bank_index"]
		assert target == item["target_area_offset"]
		key = item["physical_grid"], item["marker_area_offset"]
		assert key not in continuation_markers
		continuation_markers.add(key)

	updates = {
		(item["logical_entry"], item["physical_grid"])
		for item in plan["load_count_updates"]
	}
	assert len(updates) == len(plan["load_count_updates"])
	expected_redirects = sum(len(x["redirects"]) for x in symbolic["areas"])
	expected_continuations = sum(len(x["continuations"]) for x in symbolic["areas"])
	assert len(redirect_sources) == expected_redirects
	assert len(continuation_markers) == expected_continuations
	assert len(plan["area_writes"]) == symbolic["area_count"]

	print(f"area writes: {len(plan['area_writes'])}")
	print(f"redirects: {len(redirect_sources)}")
	print(f"continuations: {len(continuation_markers)}")
	print(f"logical load-count updates: {len(updates)}")
	print("verification: OK")


if __name__ == "__main__":
	main()
