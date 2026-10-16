#!/usr/bin/env python3
"""Build the true minimum System Card probe: one BIOS glyph, original game."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from analyze_system_card_font_slots import glyph_index

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIOS = Path(r"H:\BizHawk\Firmware\PCECD_3.0-(J).pce")
FONT_TTF = ROOT / "font" / "Galmuri11-Condensed.ttf"
OUT_BIOS = ROOT / "probes" / "SystemCard3_one_glyph_probe.pce"
OUT_MANIFEST = ROOT / "translation" / "system_card_one_glyph_probe_manifest.json"
EXPECTED_BIOS_SHA1 = "79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c"
TARGET_ORIGINAL = "出"
TARGET_REPLACEMENT = "가"
FONT_MODE = 1
FONT_OFFSET = 0x30000
GLYPH_BYTES = 18


def digest(data: bytes, algorithm: str = "sha256") -> str:
	h = hashlib.new(algorithm)
	h.update(data)
	return h.hexdigest()


def render_glyph(ch: str, font: ImageFont.FreeTypeFont) -> bytes:
	"""Encode the BIOS mode-1 12x12 glyph as six packed 24-bit row pairs."""
	image = Image.new("1", (12, 12), 0)
	draw = ImageDraw.Draw(image)
	width = font.getmask(ch).size[0]
	draw.text((max(0, (12 - width) // 2), 1), ch, font=font, fill=1)
	pixels = image.load()
	rows = []
	for y in range(12):
		row = 0
		for x in range(12):
			if pixels[x, y]:
				row |= 1 << (11 - x)
		rows.append(row)
	result = bytearray()
	for y in range(0, 12, 2):
		row0, row1 = rows[y:y + 2]
		result.extend((row0 >> 4, ((row0 & 0x0F) << 4) | (row1 >> 8), row1 & 0xFF))
	assert len(result) == GLYPH_BYTES
	return bytes(result)


def main() -> None:
	original = ORIGINAL_BIOS.read_bytes()
	if len(original) != 0x40000 or digest(original, "sha1") != EXPECTED_BIOS_SHA1:
		raise ValueError("unexpected System Card 3.0(J) image")

	sjis = TARGET_ORIGINAL.encode("shift_jis")
	index = glyph_index(sjis, original)
	if index is None:
		raise ValueError(f"EX_GETFNT rejects {TARGET_ORIGINAL!r} / {sjis.hex().upper()}")
	offset = FONT_OFFSET + index * GLYPH_BYTES
	if not FONT_OFFSET <= offset <= len(original) - GLYPH_BYTES:
		raise ValueError(f"calculated glyph offset out of range: {offset:#x}")

	replacement = render_glyph(TARGET_REPLACEMENT, ImageFont.truetype(str(FONT_TTF), 11))
	patched = bytearray(original)
	before = bytes(patched[offset:offset + GLYPH_BYTES])
	patched[offset:offset + GLYPH_BYTES] = replacement
	OUT_BIOS.write_bytes(patched)
	readback = OUT_BIOS.read_bytes()

	diff_offsets = [i for i, (a, b) in enumerate(zip(original, readback)) if a != b]
	if not diff_offsets or any(not offset <= i < offset + GLYPH_BYTES for i in diff_offsets):
		raise AssertionError("one-glyph probe changed bytes outside the declared slot")
	if readback[offset:offset + GLYPH_BYTES] != replacement:
		raise AssertionError("one-glyph readback mismatch")

	manifest = {
		"format": "SYSTEM-CARD-ONE-GLYPH-PROBE",
		"runtime_status": "PENDING",
		"purpose": "Validate the mode-1 EX_GETFNT path used by the game after correcting SJIS trail-byte compaction and the 18-byte compressed font location.",
		"game_image": "Use the completely original Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue; no game bytes are changed.",
		"original_bios_sha1": EXPECTED_BIOS_SHA1,
		"output_bios": str(OUT_BIOS),
		"output_bios_sha256": digest(readback),
		"target_original_character": TARGET_ORIGINAL,
		"target_original_sjis": sjis.hex().upper(),
		"replacement_character": TARGET_REPLACEMENT,
		"font_mode": FONT_MODE,
		"storage_format": "12x12 1bpp, two rows packed into three bytes; EX_GETFNT expands 18 bytes to 32 bytes",
		"runtime_evidence_before_rebuild": "The old mode-0/index-1721 probe kept graphics normal but left 出 unchanged.",
		"glyph_index": index,
		"bios_offset": offset,
		"slot_size": GLYPH_BYTES,
		"changed_bytes": len(diff_offsets),
		"original_slot_hex": before.hex().upper(),
		"replacement_slot_hex": replacement.hex().upper(),
		"pass_criteria": "System Card startup and game graphics remain normal, and only the original 出 glyph in the first dialogue appears as 가.",
		"fail_criteria": "Startup/global graphics corrupt, or the target 出 glyph is unchanged/garbled.",
		"next_if_pass": "Audit System Card-owned slot usage before increasing the replaced-slot count.",
		"next_if_fail": "Reject direct BIOS slot replacement and return to a runtime EX_GETFNT hook/font-RAM design.",
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"target: {TARGET_ORIGINAL} ({sjis.hex().upper()}) -> {TARGET_REPLACEMENT}")
	print(f"glyph index: {index}")
	print(f"BIOS offset: 0x{offset:05X}")
	print(f"changed bytes: {len(diff_offsets)} / {GLYPH_BYTES}")
	print(f"output: {OUT_BIOS}")


if __name__ == "__main__":
	main()
