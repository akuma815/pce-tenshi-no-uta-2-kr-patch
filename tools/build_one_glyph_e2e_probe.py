#!/usr/bin/env python3
"""Pair the exact runtime-passed one-glyph BIOS with one patched text run."""

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
EXPECTED_PASSED_BIOS_SHA256 = "212f3c96a4010bf06a13ceffd8dec92c00639188287f18376006cba67ebb8198"
BASE_CONFIG = ROOT / "translation" / "one_glyph_bizhawk_config.ini"
OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_one_glyph_e2e_probe"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "one_glyph_e2e_probe_manifest.json"
FAILED_TWO_GLYPH = ROOT / "translation" / "two_glyph_probe_manifest.json"


def main() -> None:
	if digest(ORIGINAL_BIN) != EXPECTED_BIN_SHA256:
		raise ValueError("unexpected original BIN revision")
	if digest(PASSED_BIOS) != EXPECTED_PASSED_BIOS_SHA256:
		raise ValueError("the exact runtime-passed one-glyph BIOS has changed")
	config_text = BASE_CONFIG.read_text(encoding="utf-8")
	passed_bios_json = str(PASSED_BIOS).replace("\\", "\\\\")
	if passed_bios_json not in config_text:
		raise ValueError("one-glyph BizHawk config no longer points to the passed BIOS")

	with MASTER_CSV.open(encoding="utf-8-sig", newline="") as source:
		rows = list(csv.DictReader(source))
	target = next(row for row in rows if int(row["iso_offset"], 16) == SOURCE_ISO_OFFSET)
	source_record = bytes.fromhex(target["raw_hex"])
	if not source_record.endswith(b"\x00"):
		raise ValueError("first-dialogue record lost its NUL")
	runs = parse_runs(source_record[:-1])
	text_runs = [run for run in runs if run["kind"] == "text"]
	if len(text_runs) != 6:
		raise AssertionError("first dialogue no longer has six text runs")
	first_body = text_runs[1]
	capacity = first_body["end"] - first_body["start"]
	# 8F6F is the original 出 code whose mode-1 slot displays 가 in PASSED_BIOS.
	replacement = bytes.fromhex("8F6F") + b" " * (capacity - 2)
	iso_offset = SOURCE_ISO_OFFSET + first_body["start"]
	physical = DATA_TRACK_OFFSET + iso_offset

	with ORIGINAL_BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + SOURCE_ISO_OFFSET)
		if source.read(len(source_record)) != source_record:
			raise AssertionError("master first-dialogue bytes do not match original BIN")
		source.seek(physical)
		if source.read(capacity) != first_body["data"]:
			raise AssertionError("game expected-write mismatch")

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	with OUT_BIN.open("r+b") as output:
		output.seek(physical)
		output.write(replacement)
	diffs = audit_diff(ORIGINAL_BIN, OUT_BIN, [(physical, physical + capacity)])

	cue = ORIGINAL_CUE.read_text(encoding="ascii")
	if cue.count(ORIGINAL_BIN.name) != 1:
		raise AssertionError("unexpected original CUE BIN reference count")
	OUT_CUE.write_text(cue.replace(ORIGINAL_BIN.name, OUT_BIN.name), encoding="ascii")

	if FAILED_TWO_GLYPH.exists():
		failed = json.loads(FAILED_TWO_GLYPH.read_text(encoding="utf-8"))
		failed["runtime_status"] = "FAIL"
		failed["runtime_observation"] = "System Card startup/global graphics corrupted identically."
		failed["runtime_conclusion"] = (
			"The two-glyph BIOS differs from the passed baseline at both index 1722 glyph content "
			"and the new index 1720 slot; exact-baseline E2E is required to isolate BIOS from game text."
		)
		failed["replacement_probe"] = str(OUT_CUE)
		FAILED_TWO_GLYPH.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

	manifest = {
		"format": "EXACT-PASSED-BIOS-ONE-GLYPH-E2E-PROBE",
		"runtime_status": "PENDING",
		"purpose": "Isolate game text re-encoding from every BIOS variable.",
		"bios": {
			"path": str(PASSED_BIOS), "sha256": EXPECTED_PASSED_BIOS_SHA256,
			"runtime_baseline": "PASS: original game displayed 가 at original 出 positions without global corruption.",
		},
		"game_write": {
			"master_row_id": target["id"], "iso_offset": iso_offset,
			"capacity": capacity, "expected_hex": first_body["data"].hex().upper(),
			"replacement_hex": replacement.hex().upper(), "expected_visible_text": "가",
		},
		"safety": {
			"bios_new_writes": 0, "game_expected_writes": 1,
			"game_diff_bytes": len(diffs), "speaker_runs_changed": 0,
			"control_bytes_changed": 0,
		},
		"diff_ranges": {"game_physical": coalesce_offsets(diffs)},
		"outputs": {
			"bin": str(OUT_BIN), "bin_sha256": digest(OUT_BIN),
			"cue": str(OUT_CUE), "bizhawk_config": str(BASE_CONFIG),
		},
		"pass_criteria": "Startup/game graphics remain normal and the first dialogue body displays 가.",
		"fail_criteria": "Startup/global graphics corrupt or the first body does not display 가.",
		"next_if_pass": "Game text injection is valid; isolate index 1720 using the exact passed index-1722 bytes.",
		"next_if_fail": "Reject current fixed-run game injection or configuration identity before any BIOS expansion.",
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"passed BIOS SHA-256: {EXPECTED_PASSED_BIOS_SHA256}")
	print(f"game changed bytes: {len(diffs)}")
	print(f"expected first-body glyph: 가")
	print(f"CUE: {OUT_CUE}")


if __name__ == "__main__":
	main()
