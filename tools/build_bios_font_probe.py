#!/usr/bin/env python3
"""Build a one-string probe to isolate the custom System Card glyph path."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_bios_font_diagnostic import DATA_TRACK_OFFSET, ORIGINAL_BIN, ORIGINAL_CUE, digest  # noqa: E402
from patch_iso import encode_string  # noqa: E402

PLAN = ROOT / "translation" / "fixed_length_translation_plan.json"
CHAR_MAP = ROOT / "translation" / "system_card_char_map.json"
FULL_MANIFEST = ROOT / "translation" / "bios_font_diagnostic_manifest.json"
OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_biosfont_probe.bin"
OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_biosfont_probe.cue"
OUT_MANIFEST = ROOT / "translation" / "bios_font_probe_manifest.json"
PROBE_OFFSET = 0x010B9E8


def main():
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	entry = next(x for x in plan["entries"] if x["source_offset"] == PROBE_OFFSET)
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	encoded = encode_string(entry["kept_translation"], char_map)
	capacity = entry["source_capacity_bytes"]
	if len(encoded) > capacity:
		raise AssertionError("probe translation exceeds original body")
	replacement = encoded + b"\x00" + bytes(capacity - len(encoded))

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	position = DATA_TRACK_OFFSET + PROBE_OFFSET
	with OUT_BIN.open("r+b") as target:
		target.seek(position)
		target.write(replacement)
	with OUT_BIN.open("rb") as target:
		target.seek(position)
		if target.read(len(replacement)) != replacement:
			raise AssertionError("probe readback mismatch")
	if OUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
		raise AssertionError("probe BIN size changed")

	cue = ORIGINAL_CUE.read_text(encoding="utf-8").replace(ORIGINAL_BIN.name, OUT_BIN.name, 1)
	OUT_CUE.write_text(cue, encoding="utf-8")
	manifest = {
		"format": "BIOS-FONT-ONE-STRING-PROBE",
		"purpose": "Isolate System Card glyph replacement from broad script-sheet false positives.",
		"requires_bios": str(ROOT / "probes" / "SystemCard3_KoreanFont_diagnostic.pce"),
		"source_offset": PROBE_OFFSET, "source_capacity_bytes": capacity,
		"replacement_bytes_including_nul": len(replacement),
		"kept_translation": entry["kept_translation"],
		"original_game_sha256": digest(ORIGINAL_BIN), "probe_game_sha256": digest(OUT_BIN),
		"output_bin": str(OUT_BIN), "output_cue": str(OUT_CUE),
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	if FULL_MANIFEST.exists():
		full = json.loads(FULL_MANIFEST.read_text(encoding="utf-8"))
		full["invalid_due_to_broad_runtime_corruption"] = True
		full["replacement_probe"] = str(OUT_CUE)
		FULL_MANIFEST.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
	print("probe offset:", f"{PROBE_OFFSET:07X}")
	print("patched spans: 1")
	print("replacement bytes:", len(replacement))
	print("CUE:", OUT_CUE)


if __name__ == "__main__":
	main()
