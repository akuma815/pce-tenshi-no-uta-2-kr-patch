#!/usr/bin/env python3
"""Audit alternate resident field-engine banks for a module-local fetch hook."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
OUT = ROOT / "translation" / "field_resident_hook_bank_audit.json"
DATA_TRACK_OFFSET = 7_914_480
MODULE_ISO = 0x41000
BANK_SIZE = 8192
LOAD_BASE_BANK = 0x80


def padding_runs(data, minimum=128):
	runs = []
	start = 0
	while start < len(data):
		value = data[start]
		end = start + 1
		while end < len(data) and data[end] == value:
			end += 1
		if value in (0, 0xFF) and end - start >= minimum:
			runs.append((start, end, value))
		start = end
	return runs


def main():
	candidates = []
	with BIN.open("rb") as source:
		for bank_index in range(5):
			iso_start = MODULE_ISO + bank_index * BANK_SIZE
			source.seek(DATA_TRACK_OFFSET + iso_start)
			bank = source.read(BANK_SIZE)
			assert len(bank) == BANK_SIZE
			for start, end, value in padding_runs(bank):
				mpr = 2 + bank_index
				candidates.append({
					"module_bank_index": bank_index,
					"physical_bank": f"0x{LOAD_BASE_BANK + bank_index:02X}",
					"temporary_mpr": mpr,
					"logical_start": f"0x{mpr * BANK_SIZE + start:04X}",
					"iso_start": f"0x{iso_start + start:X}",
					"fill": f"0x{value:02X}",
					"length": end - start,
					"sha_guard": bank[start:end].hex()[:64],
				})

	selected = next(
		(x for x in candidates
		 if x["physical_bank"] == "0x83" and x["logical_start"] == "0xA339"), None)
	assert selected is not None and selected["fill"] == "0xFF"
	assert selected["length"] == 7367
	result = {
		"format": "FIELD-RESIDENT-HOOK-BANK-AUDIT",
		"version": 1,
		"observed_initial_mapping": "MPR2..MPR6 = 0x80..0x84",
		"candidates": candidates,
		"selected_candidate": selected,
		"proposed_execution": {
			"trampoline_location": "original fetch body 0x4111..0x4159",
			"hook_physical_bank": "0x83",
			"hook_logical_address_after_TAM_0x20": "0xA339",
			"hook_code_window": "MPR5",
			"translated_data_window": "MPR3",
			"restore_rule": "save actual MPR5 with TMA #$20 and restore it on every return path",
		},
		"status": "static-candidate; requires loader-signature and bytecode control-flow verification before ISO mutation",
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("selected:", selected["physical_bank"], selected["logical_start"],
	      selected["iso_start"], selected["length"], "bytes")
	print("output:", OUT)


if __name__ == "__main__":
	main()
