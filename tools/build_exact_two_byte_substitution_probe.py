#!/usr/bin/env python3
"""Replace exactly two original text bytes with the proven 8F6F Hangul code."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_current_translation_probe import (  # noqa: E402
	DATA_TRACK_OFFSET,
	EXPECTED_BIN_SHA256,
	MASTER_CSV,
	ORIGINAL_BIN,
	ORIGINAL_CUE,
	SOURCE_ISO_OFFSET,
	audit_diff,
	coalesce_offsets,
	digest,
	parse_runs,
)

PASSED_BIOS = ROOT / "probes" / "SystemCard3_one_glyph_probe.pce"
EXPECTED_BIOS_SHA256 = "212f3c96a4010bf06a13ceffd8dec92c00639188287f18376006cba67ebb8198"
CONFIG = ROOT / "translation" / "one_glyph_bizhawk_config.ini"
OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_exact_substitution_probe"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "exact_substitution_probe_manifest.json"
PREVIOUS_MANIFEST = ROOT / "translation" / "one_glyph_e2e_probe_manifest.json"


def main() -> None:
	if digest(ORIGINAL_BIN) != EXPECTED_BIN_SHA256:
		raise ValueError("unexpected original BIN revision")
	if digest(PASSED_BIOS) != EXPECTED_BIOS_SHA256:
		raise ValueError("runtime-passed BIOS changed")

	with MASTER_CSV.open(encoding="utf-8-sig", newline="") as source:
		rows = list(csv.DictReader(source))
	row = next(x for x in rows if int(x["iso_offset"], 16) == SOURCE_ISO_OFFSET)
	record = bytes.fromhex(row["raw_hex"])
	if not record.endswith(b"\x00"):
		raise ValueError("first dialogue lost its terminator")
	text_runs = [x for x in parse_runs(record[:-1]) if x["kind"] == "text"]
	if len(text_runs) != 6:
		raise AssertionError("unexpected first-dialogue structure")
	body = text_runs[1]
	if body["data"] != bytes.fromhex("6F2D8141BCB5DD"):
		raise AssertionError("first body is no longer よう、シオン")

	# Replace only よう (6F 2D). Keep 、シオン and every following byte exact.
	iso_offset = SOURCE_ISO_OFFSET + body["start"]
	physical = DATA_TRACK_OFFSET + iso_offset
	expected = bytes.fromhex("6F2D")
	replacement = bytes.fromhex("8F6F")
	with ORIGINAL_BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + SOURCE_ISO_OFFSET)
		if source.read(len(record)) != record:
			raise AssertionError("master record does not match original BIN")
		source.seek(physical)
		if source.read(2) != expected:
			raise AssertionError("Expected Write source mismatch")

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	with OUT_BIN.open("r+b") as output:
		output.seek(physical)
		output.write(replacement)
	diffs = audit_diff(ORIGINAL_BIN, OUT_BIN, [(physical, physical + 2)])
	if len(diffs) != 2:
		raise AssertionError(f"expected exactly two changed bytes, found {len(diffs)}")

	cue = ORIGINAL_CUE.read_text(encoding="ascii")
	if cue.count(ORIGINAL_BIN.name) != 1:
		raise AssertionError("unexpected CUE BIN reference count")
	OUT_CUE.write_text(cue.replace(ORIGINAL_BIN.name, OUT_BIN.name), encoding="ascii")

	if PREVIOUS_MANIFEST.exists():
		previous = json.loads(PREVIOUS_MANIFEST.read_text(encoding="utf-8"))
		previous["runtime_status"] = "PARTIAL_PASS"
		previous["runtime_observation"] = (
			"Hangul rendered and graphics remained normal, but ASCII 0x20 padding left/combined "
			"dialogue rows across the page transition."
		)
		previous["runtime_conclusion"] = (
			"BIOS glyph and 8F6F text consumption pass; ASCII-space padding policy fails this renderer."
		)
		previous["replacement_probe"] = str(OUT_CUE)
		PREVIOUS_MANIFEST.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

	manifest = {
		"format": "EXACT-TWO-BYTE-SUBSTITUTION-PROBE",
		"runtime_status": "PENDING",
		"purpose": "Validate Hangul substitution without introducing any padding byte.",
		"bios": {"path": str(PASSED_BIOS), "sha256": EXPECTED_BIOS_SHA256, "new_writes": 0},
		"game_write": {
			"master_row_id": row["id"], "iso_offset": iso_offset,
			"expected_hex": expected.hex().upper(), "replacement_hex": replacement.hex().upper(),
			"original_body_hex": body["data"].hex().upper(),
			"result_body_hex": (replacement + body["data"][2:]).hex().upper(),
			"expected_visible_text": "가、シオン",
		},
		"safety": {
			"game_expected_writes": 1, "game_diff_bytes": len(diffs),
			"padding_bytes_added": 0, "control_bytes_changed": 0,
			"speaker_bytes_changed": 0, "terminator_changed": False,
		},
		"diff_ranges": {"game_physical": coalesce_offsets(diffs)},
		"outputs": {
			"bin": str(OUT_BIN), "bin_sha256": digest(OUT_BIN),
			"cue": str(OUT_CUE), "bizhawk_config": str(CONFIG),
		},
		"pass_criteria": "Normal graphics/page transition and first body reads 가、シオン.",
		"fail_criteria": "Global corruption, page overlap, or failure to display 가.",
		"next_if_pass": "Adopt exact encoded-byte-budget substitution; do not use ASCII padding.",
		"next_if_fail": "Trace the page-clear state; do not expand translation or BIOS mapping.",
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print("game write: 6F2D -> 8F6F")
	print("expected body: 가、シオン")
	print(f"changed bytes: {len(diffs)}")
	print(f"CUE: {OUT_CUE}")


if __name__ == "__main__":
	main()
