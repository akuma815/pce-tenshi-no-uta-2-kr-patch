#!/usr/bin/env python3
"""Model System Card 3.0 EX_GETFNT and select unused SJIS slots for Hangul."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIOS = ROOT / "probes" / "SystemCard3_original_noheader.pce"
TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
OUT = ROOT / "translation" / "system_card_font_slot_audit.json"
TABLE_OFFSET = 0x127E  # logical F27E in physical bank 0
FONT_OFFSET = 0x10000
GLYPH_BYTES = 32
GLYPH_COUNT = 6144


def sjis_to_jis(code):
	lead, trail = code
	a = lead - 0x81
	if not 0 <= a < 0x6F or 0x1F <= a < 0x3F:
		return None
	if a >= 0x40:
		a -= 0x40
	row = 0x21 + a * 2
	a = trail - 0x40
	if not 0 <= a < 0xBD or a == 0x3F:
		return None
	# BIOS F203..F20A skips 0x7F by incrementing the lower trail half,
	# not the upper half.  The old condition was reversed and mapped most
	# characters to the adjacent glyph (e.g. 出: 1721 instead of 1722).
	if a < 0x3F:
		a += 1
	if a >= 0x5F:
		row += 1
		cell = a - 0x3E
	else:
		cell = a + 0x20
	return row, cell


def compact_position(row, cell):
	# Exact row/cell filtering and compaction from System Card 3.0 F21D..F261.
	if row == 0x23:
		if cell >= 0x61:
			cell -= 0x06
		if cell >= 0x41:
			cell -= 0x07
		cell -= 0x0F
	elif row == 0x26:
		if cell >= 0x41:
			cell -= 0x08
	elif row == 0x27:
		if cell >= 0x51:
			cell -= 0x0F
	elif row < 0x28:
		pass
	elif row < 0x30 or row >= 0x50:
		return None
	else:
		row -= 0x08
	if not 0x21 <= cell <= 0x7E:
		return None
	return row, cell


def glyph_index(code, bios):
	jis = sjis_to_jis(code)
	if jis is None:
		return None
	compact = compact_position(*jis)
	if compact is None:
		return None
	row, cell = compact
	y = (row - 0x21) * 2
	if not 0 <= y + 1 < 0x100:
		return None
	base = bios[TABLE_OFFSET + y] | bios[TABLE_OFFSET + y + 1] << 8
	index = base + cell - 0x21
	return index if 0 <= index < GLYPH_COUNT else None


def encoded_pairs(text):
	data = text.encode("shift_jis", errors="ignore")
	i = 0
	while i + 1 < len(data):
		if (0x81 <= data[i] <= 0x9F) or (0xE0 <= data[i] <= 0xEF):
			yield bytes(data[i:i + 2])
			i += 2
		else:
			i += 1


def main():
	bios = BIOS.read_bytes()
	if len(bios) != 262144:
		raise ValueError("unexpected System Card size")
	if glyph_index("出".encode("shift_jis"), bios) != 1722:
		raise AssertionError("System Card SJIS conversion regression for 出 / 8F6F")
	valid = {}
	for lead in list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)):
		for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
			code = bytes((lead, trail))
			index = glyph_index(code, bios)
			if index is not None:
				valid.setdefault(index, code)

	protected_codes = set()
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			protected_codes.update(encoded_pairs(row["원문"]))
			protected_codes.update(encoded_pairs(row["번역"]))
	protected_indices = {glyph_index(code, bios) for code in protected_codes}
	protected_indices.discard(None)

	hangul = list(json.loads(CHAR_MAP.read_text(encoding="utf-8")))
	candidates = [(index, code) for index, code in sorted(valid.items(), reverse=True)
	              if index not in protected_indices]
	if len(candidates) < len(hangul):
		raise ValueError(f"only {len(candidates)} unused slots for {len(hangul)} Hangul glyphs")
	selected = candidates[:len(hangul)]
	assert len({x[0] for x in selected}) == len(selected)
	assert all(FONT_OFFSET <= FONT_OFFSET + i * GLYPH_BYTES <= len(bios) - GLYPH_BYTES
	           for i, _ in selected)

	result = {
		"format": "SYSTEM-CARD-FONT-SLOT-AUDIT",
		"bios_path": str(BIOS), "bios_size": len(bios),
		"font_offset": FONT_OFFSET, "glyph_bytes": GLYPH_BYTES, "glyph_capacity": GLYPH_COUNT,
		"valid_unique_glyph_indices": len(valid),
		"protected_glyph_indices": len(protected_indices),
		"unused_candidate_indices": len(candidates), "hangul_glyphs": len(hangul),
		"selected": [{"hangul": ch, "sjis": code.hex().upper(), "glyph_index": index,
		              "bios_offset": FONT_OFFSET + index * GLYPH_BYTES}
		             for ch, (index, code) in zip(hangul, selected)],
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("valid unique glyph indices:", result["valid_unique_glyph_indices"])
	print("protected indices:", result["protected_glyph_indices"])
	print("unused candidates:", result["unused_candidate_indices"])
	print("selected Hangul slots:", len(result["selected"]))
	print("output:", OUT)


if __name__ == "__main__":
	main()
