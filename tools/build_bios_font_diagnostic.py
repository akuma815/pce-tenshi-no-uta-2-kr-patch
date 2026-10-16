#!/usr/bin/env python3
"""Build separate fixed-length game and Korean System Card diagnostic images."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from patch_iso import encode_string  # noqa: E402

ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
ORIGINAL_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
ORIGINAL_BIOS = Path(r"H:\BizHawk\Firmware\PCECD_3.0-(J).pce")
AUDIT = ROOT / "translation" / "system_card_font_slot_audit.json"
PLAN = ROOT / "translation" / "fixed_length_translation_plan.json"
FONT_TTF = ROOT / "font" / "Galmuri11-Condensed.ttf"
OUT_MAP = ROOT / "translation" / "system_card_char_map.json"
OUT_BIOS = ROOT / "probes" / "SystemCard3_KoreanFont_diagnostic.pce"
OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_biosfont_diagnostic.bin"
OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_biosfont_diagnostic.cue"
OUT_MANIFEST = ROOT / "translation" / "bios_font_diagnostic_manifest.json"
DATA_TRACK_OFFSET = 7_914_480
EXPECTED_BIOS_SHA1 = "79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c"


def digest(path, algorithm="sha256"):
	h = hashlib.new(algorithm)
	with path.open("rb") as source:
		for chunk in iter(lambda: source.read(1024 * 1024), b""):
			h.update(chunk)
	return h.hexdigest()


def render_glyph(ch, font):
	img = Image.new("1", (16, 16), 0)
	draw = ImageDraw.Draw(img)
	mask = font.getmask(ch)
	w, _ = mask.size
	draw.text((max(0, (12 - w) // 2), 1), ch, font=font, fill=1)
	pixels = img.load()
	out = bytearray(32)
	for y in range(16):
		for x in range(16):
			if pixels[x, y]:
				out[y * 2 + x // 8] |= 1 << (7 - x % 8)
	return bytes(out)


def main():
	if digest(ORIGINAL_BIOS, "sha1") != EXPECTED_BIOS_SHA1:
		raise ValueError("System Card 3.0(J) SHA-1 mismatch")
	audit = json.loads(AUDIT.read_text(encoding="utf-8"))
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	selected = audit["selected"]
	if len(selected) != 896:
		raise ValueError("diagnostic requires exactly 896 mapped glyphs")
	char_map = {x["hangul"]: x["sjis"] for x in selected}
	OUT_MAP.write_text(json.dumps(char_map, ensure_ascii=False, indent=2), encoding="utf-8")

	font = ImageFont.truetype(str(FONT_TTF), 11)
	bios = bytearray(ORIGINAL_BIOS.read_bytes())
	original_bios = bytes(bios)
	spans = []
	for item in selected:
		offset = item["bios_offset"]
		glyph = render_glyph(item["hangul"], font)
		if not 0x10000 <= offset <= len(bios) - 32:
			raise ValueError(f"glyph offset out of range: {offset:#x}")
		bios[offset:offset + 32] = glyph
		spans.append((offset, offset + 32))
	OUT_BIOS.write_bytes(bios)
	written_bios = OUT_BIOS.read_bytes()
	for start, end in spans:
		assert written_bios[start:end] == bios[start:end]

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	writes = []
	with OUT_BIN.open("r+b") as target:
		for entry in plan["entries"]:
			encoded = encode_string(entry["kept_translation"], char_map)
			capacity = entry["source_capacity_bytes"]
			if len(encoded) > capacity:
				raise AssertionError(f'fixed-length overflow at {entry["source_offset"]:07X}')
			data = encoded + b"\x00" + bytes(capacity - len(encoded))
			position = DATA_TRACK_OFFSET + entry["source_offset"]
			target.seek(position)
			target.write(data)
			writes.append((position, data))
	with OUT_BIN.open("rb") as target:
		for position, data in writes:
			target.seek(position)
			if target.read(len(data)) != data:
				raise AssertionError(f"game readback mismatch at {position:#x}")
	if OUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
		raise AssertionError("diagnostic BIN size changed")

	cue = ORIGINAL_CUE.read_text(encoding="utf-8")
	cue = cue.replace(ORIGINAL_BIN.name, OUT_BIN.name, 1)
	OUT_CUE.write_text(cue, encoding="utf-8")
	manifest = {
		"format": "BIOS-FONT-FIXED-LENGTH-DIAGNOSTIC",
		"warning": "Diagnostic only. Requires the paired custom System Card and contains automatically truncated translations.",
		"original_bios_sha1": EXPECTED_BIOS_SHA1,
		"patched_bios_sha256": digest(OUT_BIOS),
		"original_game_sha256": digest(ORIGINAL_BIN),
		"patched_game_sha256": digest(OUT_BIN),
		"glyphs_replaced": len(selected),
		"bios_changed_bytes": sum(a != b for a, b in zip(original_bios, bios)),
		"translation_writes": len(writes),
		"truncated_entries": plan["truncated_entries"],
		"outputs": {"bios": str(OUT_BIOS), "bin": str(OUT_BIN), "cue": str(OUT_CUE), "char_map": str(OUT_MAP)},
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print("glyphs replaced:", manifest["glyphs_replaced"])
	print("BIOS changed bytes:", manifest["bios_changed_bytes"])
	print("translation writes:", manifest["translation_writes"])
	print("truncated entries:", manifest["truncated_entries"])
	print("BIOS:", OUT_BIOS)
	print("CUE:", OUT_CUE)


if __name__ == "__main__":
	main()
