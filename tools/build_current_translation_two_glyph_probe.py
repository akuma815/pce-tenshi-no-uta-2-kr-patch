#!/usr/bin/env python3
"""Build the next minimal gate: two Hangul glyphs near proven mode-1 slot 1722."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_system_card_font_slots import glyph_index  # noqa: E402
from build_current_translation_probe import (  # noqa: E402
	BASE_CONFIG,
	DATA_TRACK_OFFSET,
	EXPECTED_BIN_SHA256,
	EXPECTED_BIOS_SHA1,
	FONT_OFFSET,
	GLYPH_BYTES,
	MASTER_CSV,
	ORIGINAL_BIN,
	ORIGINAL_BIOS,
	ORIGINAL_CUE,
	SOURCE_ISO_OFFSET,
	audit_diff,
	coalesce_offsets,
	digest,
	parse_runs,
	render_glyph,
)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_two_glyph_probe"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_BIOS = ROOT / "probes" / "SystemCard3_KoreanFont_two_glyph_probe.pce"
OUT_CONFIG = ROOT / "translation" / "two_glyph_probe_bizhawk_config.ini"
OUT_MANIFEST = ROOT / "translation" / "two_glyph_probe_manifest.json"
FAILED_MANIFEST = ROOT / "translation" / "current_translation_probe_manifest.json"
FONT_TTF = ROOT / "font" / "Galmuri11-Condensed.ttf"

# Index 1722 is the exact slot that passed the one-glyph runtime test. Index
# 1720 is the nearest unreferenced compact index in the extracted corpus. Both
# are ordinary adjacent JIS kanji slots, unlike the failed 3443..3460 tail.
MAPPING = {
	"여": {"sjis": bytes.fromhex("8F6F"), "expected_index": 1722},
	"어": {"sjis": bytes.fromhex("8F6D"), "expected_index": 1720},
}


def main() -> None:
	if digest(ORIGINAL_BIN) != EXPECTED_BIN_SHA256:
		raise ValueError("unexpected original BIN revision")
	if digest(ORIGINAL_BIOS, "sha1") != EXPECTED_BIOS_SHA1:
		raise ValueError("unexpected System Card 3.0(J) revision")

	with MASTER_CSV.open(encoding="utf-8-sig", newline="") as source:
		rows = list(csv.DictReader(source))
	target = next(row for row in rows if int(row["iso_offset"], 16) == SOURCE_ISO_OFFSET)
	source_record = bytes.fromhex(target["raw_hex"])
	if not source_record.endswith(b"\x00"):
		raise ValueError("first-dialogue source lost its terminator")
	source_bytes = source_record[:-1]
	runs = parse_runs(source_bytes)
	text_runs = [run for run in runs if run["kind"] == "text"]
	if len(text_runs) != 6:
		raise AssertionError("first dialogue no longer has six text runs")
	first_body = text_runs[1]
	if "여어" not in target["translation"]:
		raise ValueError("current translation no longer contains the two-glyph probe text")

	bios_original = ORIGINAL_BIOS.read_bytes()
	font = ImageFont.truetype(str(FONT_TTF), 11)
	bios_writes = []
	for ch, item in MAPPING.items():
		index = glyph_index(item["sjis"], bios_original)
		if index != item["expected_index"]:
			raise AssertionError(f"SJIS/index regression for {ch}: {index}")
		offset = FONT_OFFSET + index * GLYPH_BYTES
		bios_writes.append({
			"owner": f"glyph:{ch}", "offset": offset,
			"expected": bios_original[offset:offset + GLYPH_BYTES],
			"replacement": render_glyph(ch, font),
			"sjis": item["sjis"], "glyph_index": index,
		})

	bios_patched = bytearray(bios_original)
	for write in bios_writes:
		start = write["offset"]
		if bytes(bios_patched[start:start + GLYPH_BYTES]) != write["expected"]:
			raise AssertionError(f'BIOS expected-write mismatch for {write["owner"]}')
		bios_patched[start:start + GLYPH_BYTES] = write["replacement"]
	OUT_BIOS.write_bytes(bios_patched)
	bios_diff = audit_diff(
		ORIGINAL_BIOS, OUT_BIOS,
		[(x["offset"], x["offset"] + GLYPH_BYTES) for x in bios_writes],
	)

	encoded = MAPPING["여"]["sjis"] + MAPPING["어"]["sjis"]
	capacity = first_body["end"] - first_body["start"]
	if len(encoded) > capacity:
		raise AssertionError("two-glyph text exceeds the original first-body run")
	replacement = encoded + b" " * (capacity - len(encoded))
	game_write = {
		"owner": "first_dialogue_body_1_two_glyph_gate",
		"iso_offset": SOURCE_ISO_OFFSET + first_body["start"],
		"expected": first_body["data"], "replacement": replacement,
	}

	physical_source = DATA_TRACK_OFFSET + SOURCE_ISO_OFFSET
	with ORIGINAL_BIN.open("rb") as source:
		source.seek(physical_source)
		if source.read(len(source_record)) != source_record:
			raise AssertionError("master first-dialogue bytes do not match original BIN")
		position = DATA_TRACK_OFFSET + game_write["iso_offset"]
		source.seek(position)
		if source.read(len(game_write["expected"])) != game_write["expected"]:
			raise AssertionError("game expected-write mismatch")

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	position = DATA_TRACK_OFFSET + game_write["iso_offset"]
	with OUT_BIN.open("r+b") as target_file:
		target_file.seek(position)
		target_file.write(game_write["replacement"])
	game_diff = audit_diff(
		ORIGINAL_BIN, OUT_BIN,
		[(position, position + len(game_write["replacement"]))],
	)

	cue_text = ORIGINAL_CUE.read_text(encoding="ascii")
	if cue_text.count(ORIGINAL_BIN.name) != 1:
		raise AssertionError("unexpected original CUE BIN reference count")
	OUT_CUE.write_text(cue_text.replace(ORIGINAL_BIN.name, OUT_BIN.name), encoding="ascii")

	config = BASE_CONFIG.read_text(encoding="utf-8")
	old_bios = str(ROOT / "probes" / "SystemCard3_one_glyph_probe.pce").replace("\\", "\\\\")
	new_bios = str(OUT_BIOS).replace("\\", "\\\\")
	config = config.replace(old_bios, new_bios)
	if new_bios not in config:
		raise AssertionError("failed to update BizHawk firmware override")
	OUT_CONFIG.write_text(config, encoding="utf-8")

	if FAILED_MANIFEST.exists():
		failed = json.loads(FAILED_MANIFEST.read_text(encoding="utf-8"))
		failed["runtime_status"] = "FAIL"
		failed["runtime_observation"] = "System Card startup/global graphics corrupted before gameplay."
		failed["runtime_conclusion"] = (
			"Indices 3443..3460 at BIOS 0x3F216..0x3F348 are not proven replaceable "
			"font-only storage; reachable compact indices cannot be treated as free BIOS slots."
		)
		failed["replacement_probe"] = str(OUT_CUE)
		FAILED_MANIFEST.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

	manifest = {
		"format": "SYSTEM-CARD-MODE1-TWO-GLYPH-GATE",
		"runtime_status": "PENDING",
		"purpose": "Distinguish unsafe high-index BIOS storage from multi-glyph/text-path failure.",
		"input": {
			"original_bin_sha256": EXPECTED_BIN_SHA256,
			"original_bios_sha1": EXPECTED_BIOS_SHA1,
			"master_row_id": target["id"], "source_iso_offset": SOURCE_ISO_OFFSET,
		},
		"mapping": {
			ch: {"sjis": item["sjis"].hex().upper(), "glyph_index": item["glyph_index"],
			     "bios_offset": item["offset"]}
			for ch, item in zip(MAPPING, bios_writes)
		},
		"game_write": {
			"iso_offset": game_write["iso_offset"], "capacity": capacity,
			"expected_hex": game_write["expected"].hex().upper(),
			"replacement_hex": game_write["replacement"].hex().upper(),
			"visible_text": "여어",
		},
		"safety": {
			"font_mode": 1, "glyph_bytes": GLYPH_BYTES,
			"bios_expected_writes": 2, "bios_diff_bytes": len(bios_diff),
			"game_expected_writes": 1, "game_diff_bytes": len(game_diff),
			"speaker_runs_changed": 0, "control_bytes_changed": 0,
		},
		"diff_ranges": {"bios": coalesce_offsets(bios_diff), "game_physical": coalesce_offsets(game_diff)},
		"outputs": {
			"bios": str(OUT_BIOS), "bios_sha256": digest(OUT_BIOS),
			"bin": str(OUT_BIN), "bin_sha256": digest(OUT_BIN),
			"cue": str(OUT_CUE), "bizhawk_config": str(OUT_CONFIG),
		},
		"pass_criteria": "Startup/game graphics remain normal and the first dialogue body displays 여어.",
		"fail_criteria": "Startup/global graphics corrupt, or the first dialogue does not display the two mapped glyphs.",
		"next_if_pass": "Expand only within a runtime-proven contiguous ordinary-kanji slot window.",
		"next_if_fail": "Keep only index 1722 and test index 1720 independently; do not expand BIOS slot replacement.",
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print("mapping: 여=8F6F/index1722, 어=8F6D/index1720")
	print(f"BIOS changed bytes: {len(bios_diff)}")
	print(f"game changed bytes: {len(game_diff)}")
	print(f"BIOS: {OUT_BIOS}")
	print(f"CUE: {OUT_CUE}")


if __name__ == "__main__":
	main()
