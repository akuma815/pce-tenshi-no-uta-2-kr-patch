#!/usr/bin/env python3
"""Audit the field engine MPR2 bank for a safe module-local hook cave."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
OUT = ROOT / "translation" / "field_hook_padding_audit.json"
DATA_TRACK_OFFSET = 7_914_480
ISO_OFFSET = 0x41000
LOGICAL_BASE = 0x4000
BANK_SIZE = 8192


def runs(data, minimum=8):
	result = []
	start = 0
	while start < len(data):
		end = start + 1
		while end < len(data) and data[end] == data[start]:
			end += 1
		if end - start >= minimum:
			result.append({
				"value": f"0x{data[start]:02X}",
				"logical_start": f"0x{LOGICAL_BASE + start:04X}",
				"iso_start": f"0x{ISO_OFFSET + start:X}",
				"length": end - start,
			})
		start = end
	return result


def main():
	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + ISO_OFFSET)
		bank = source.read(BANK_SIZE)
	assert len(bank) == BANK_SIZE

	jump_targets = []
	for offset in range(0, 0x48, 3):
		if bank[offset] == 0x4C:
			target = bank[offset + 1] | bank[offset + 2] << 8
			jump_targets.append({
				"entry": f"0x{LOGICAL_BASE + offset:04X}",
				"target": f"0x{target:04X}",
			})

	repeated = sorted(runs(bank), key=lambda x: x["length"], reverse=True)
	zero_ff = [x for x in repeated if x["value"] in ("0x00", "0xFF")]
	result = {
		"format": "FIELD-HOOK-PADDING-AUDIT",
		"module": "field engine MPR2",
		"logical_range": "0x4000..0x5FFF",
		"iso_range": "0x41000..0x42FFF",
		"original_fetch_signature": bank[0x111:0x15A].hex(),
		"jump_table": jump_targets,
		"repeated_runs_at_least_8": repeated,
		"zero_or_ff_runs_at_least_8": zero_ff,
		"largest_zero_or_ff_run": max((x["length"] for x in zero_ff), default=0),
		"safe_padding_candidate": None,
		"conclusion": "No verified padding cave; perform API call-graph/liveness audit before reclaiming code.",
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("largest zero/FF run:", result["largest_zero_or_ff_run"], "bytes")
	print("safe padding candidate: NONE")
	print("output:", OUT)


if __name__ == "__main__":
	main()
