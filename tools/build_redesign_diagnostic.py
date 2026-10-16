#!/usr/bin/env python3
"""Build a guarded fetch-only redesign diagnostic BIN/CUE.

This never overwrites the original or the older patched build.  The result is not a
release: the redesigned local glyph hook is intentionally not implemented yet.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
SOURCE_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_redesign_diagnostic.bin"
OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_redesign_diagnostic.cue"
PLAN = ROOT / "translation" / "area_patch_plan_materialized.json"
HOOK_MANIFEST = ROOT / "translation" / "field_fetch_hook_prototype.json"
TRAMP = ROOT / "translation" / "field_fetch_trampoline.bin"
HOOK = ROOT / "translation" / "field_fetch_hook.bin"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT_MANIFEST = ROOT / "translation" / "redesign_diagnostic_build.json"

DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
AREA_TABLE = 0x424A5
FIELD_START_LBA = 130
FIRST_AREA_LBA = 162
EXPECTED_FIELD_SECTORS = 32
EXPECTED_FIELD_BANKS = 8


def sha256(path):
	h = hashlib.sha256()
	with path.open("rb") as f:
		for chunk in iter(lambda: f.read(4 << 20), b""):
			h.update(chunk)
	return h.hexdigest()


def add_patch(patches, iso_offset, data, kind):
	assert data
	patches.append((iso_offset, bytes(data), kind))


def verify_nonoverlap(patches):
	ordered = sorted(patches)
	for (a_start, a_data, a_kind), (b_start, _, b_kind) in zip(ordered, ordered[1:]):
		a_end = a_start + len(a_data)
		if a_end > b_start:
			raise ValueError(
				f"patch overlap {a_kind} {a_start:#x}..{a_end:#x} / {b_kind} {b_start:#x}")
	return ordered


def main():
	assert FIRST_AREA_LBA - FIELD_START_LBA == EXPECTED_FIELD_SECTORS
	assert EXPECTED_FIELD_SECTORS * SECTOR // 8192 == EXPECTED_FIELD_BANKS
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	hook_manifest = json.loads(HOOK_MANIFEST.read_text(encoding="utf-8"))
	assert plan["format"] == "KAPLAN1-MATERIALIZED"
	assert hook_manifest["dry_run_only"] is True

	patches = []
	for area in plan["area_writes"]:
		base = area["lba"] * SECTOR
		for write in area["writes"]:
			add_patch(patches, base + write["area_relative_offset"],
			          bytes.fromhex(write["data_hex"]), f"grid{area['physical_grid']:02d}:data")
			start = base + write["area_relative_offset"]
			end = start + write["length"]
			if any(start < (x["lba"] + x["load_sectors"]) * SECTOR
			       and end > x["lba"] * SECTOR for x in overlay["entries"]):
				raise ValueError(
					f"primary package write overlaps live overlay loader range: "
					f"grid{area['physical_grid']:02d} {start:#x}..{end:#x}")
	for item in plan["continuation_records"]:
		area = next(x for x in plan["area_writes"] if x["physical_grid"] == item["physical_grid"])
		add_patch(patches, area["lba"] * SECTOR + item["marker_area_offset"],
		          bytes.fromhex(item["record_hex"]), f"grid{item['physical_grid']:02d}:continuation")
	for item in plan["redirect_records"]:
		add_patch(patches, item["source_iso_offset"], bytes.fromhex(item["record_hex"]),
		          f"grid{item['physical_grid']:02d}:redirect")
	for item in plan["load_count_updates"]:
		assert 0 <= item["new_sectors"] <= 96
		add_patch(patches, AREA_TABLE + item["logical_entry"] * 4 + 3,
		          bytes((item["new_sectors"],)), f"area-table:{item['logical_entry']}")

	tramp = TRAMP.read_bytes()
	hook = HOOK.read_bytes()
	add_patch(patches, int(hook_manifest["trampoline"]["iso_offset"], 16), tramp, "fetch-trampoline")
	add_patch(patches, int(hook_manifest["hook"]["iso_offset"], 16), hook, "fetch-hook")
	ordered = verify_nonoverlap(patches)

	# Guard every original byte that has a known expected value before copying/mutating.
	with SOURCE_BIN.open("rb") as source:
		tramp_iso = int(hook_manifest["trampoline"]["iso_offset"], 16)
		source.seek(DATA_TRACK_OFFSET + tramp_iso)
		assert source.read(len(tramp)) == bytes.fromhex(hook_manifest["trampoline"]["original_hex"])
		hook_iso = int(hook_manifest["hook"]["iso_offset"], 16)
		source.seek(DATA_TRACK_OFFSET + hook_iso)
		assert source.read(len(hook)) == bytes((0xFF,)) * len(hook)
		for item in plan["load_count_updates"]:
			offset = AREA_TABLE + item["logical_entry"] * 4 + 3
			source.seek(DATA_TRACK_OFFSET + offset)
			assert source.read(1) == bytes((item["old_sectors"],))

	source_hash = sha256(SOURCE_BIN)
	shutil.copyfile(SOURCE_BIN, OUT_BIN)
	with OUT_BIN.open("r+b") as output:
		for iso_offset, data, _ in ordered:
			output.seek(DATA_TRACK_OFFSET + iso_offset)
			output.write(data)

	assert OUT_BIN.stat().st_size == SOURCE_BIN.stat().st_size
	with OUT_BIN.open("rb") as output:
		for iso_offset, data, kind in ordered:
			output.seek(DATA_TRACK_OFFSET + iso_offset)
			assert output.read(len(data)) == data, kind

	cue = SOURCE_CUE.read_text(encoding="ascii")
	cue = cue.replace(SOURCE_BIN.name, OUT_BIN.name)
	assert OUT_BIN.name in cue and SOURCE_BIN.name not in cue
	OUT_CUE.write_text(cue, encoding="ascii", newline="\r\n")
	output_hash = sha256(OUT_BIN)
	manifest = {
		"format": "REDESIGN-DIAGNOSTIC-BUILD",
		"release_safe": False,
		"purpose": "fetch/redirect/continuation/token execution only; local glyph hook missing",
		"source_sha256": source_hash,
		"output_sha256": output_hash,
		"output_bin": OUT_BIN.name,
		"output_cue": OUT_CUE.name,
		"patch_spans": len(ordered),
		"patched_bytes": sum(len(x[1]) for x in ordered),
		"field_loader_proof": {
			"field_lba_start": FIELD_START_LBA,
			"first_area_lba": FIRST_AREA_LBA,
			"sectors": EXPECTED_FIELD_SECTORS,
			"banks": EXPECTED_FIELD_BANKS,
			"observed_initial_physical_mapping": "0x80..0x84 in MPR2..MPR6",
			"selected_hook_bank": "fourth field bank = 0x83",
		},
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
	print("patch spans:", manifest["patch_spans"])
	print("patched bytes:", manifest["patched_bytes"])
	print("source sha256:", source_hash)
	print("output sha256:", output_hash)
	print("diagnostic BIN:", OUT_BIN)
	print("WARNING: fetch-only diagnostic; not release-safe")


if __name__ == "__main__":
	main()
