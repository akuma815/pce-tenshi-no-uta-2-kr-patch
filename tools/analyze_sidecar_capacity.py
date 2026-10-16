#!/usr/bin/env python3
"""Audit global translated-string and font capacity against the 150-sector sidecar."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from patch_iso import encode_string  # noqa: E402

TSV = ROOT / "translation" / "script_sheet.tsv"
CHAR_MAP = ROOT / "translation" / "char_map.json"
FONT = ROOT / "translation" / "font_data.bin"
OUT = ROOT / "translation" / "sidecar_capacity.json"
BANK = 8192
SECTOR = 2048
SIDECAR_SECTORS = 150
SIDECAR_BYTES = SIDECAR_SECTORS * SECTOR
HEADER_RESERVE = 2048
TOKEN_TABLE_RESERVE = 50


def bank_safe_size(chunks, start):
	position = start
	padding = 0
	for chunk in chunks:
		inside = position % BANK
		if inside + len(chunk) > BANK:
			pad = BANK - inside
			position += pad
			padding += pad
		position += len(chunk)
	return position, padding


def main():
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	encoded_rows = []
	used_glyphs = set()
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			text = row["번역"].strip()
			if not text:
				continue
			data = encode_string(text, char_map) + b"\x00"
			if len(data) > BANK:
				raise ValueError(f"string crosses entire bank: {row['키(ISO오프셋)']} {len(data)}")
			encoded_rows.append(data)
			used_glyphs.update(ch for ch in text if ch in char_map)

	unique = sorted(set(encoded_rows), key=len, reverse=True)
	string_end, string_padding = bank_safe_size(unique, HEADER_RESERVE)
	string_pool_bytes = string_end - HEADER_RESERVE
	full_font = FONT.stat().st_size
	full_font_start = math.ceil(string_end / BANK) * BANK
	total_full_font = full_font_start + full_font + TOKEN_TABLE_RESERVE
	subset_font = len(used_glyphs) * 32
	# A compact subset needs at least code(2)+index(2) per glyph.
	subset_map = len(used_glyphs) * 4
	total_subset_font = full_font_start + subset_font + subset_map + TOKEN_TABLE_RESERVE

	result = {
		"format": "SIDECAR-CAPACITY-AUDIT",
		"sidecar_sectors": SIDECAR_SECTORS,
		"sidecar_bytes": SIDECAR_BYTES,
		"translated_rows": len(encoded_rows),
		"unique_strings": len(unique),
		"raw_row_string_bytes": sum(map(len, encoded_rows)),
		"deduplicated_string_bytes": sum(map(len, unique)),
		"bank_padding_bytes": string_padding,
		"string_pool_with_padding": string_pool_bytes,
		"largest_string_bytes": max(map(len, unique), default=0),
		"used_glyphs": len(used_glyphs),
		"full_font_bytes": full_font,
		"compact_subset_font_bytes": subset_font,
		"compact_subset_map_bytes": subset_map,
		"header_reserve_bytes": HEADER_RESERVE,
		"token_table_reserve_bytes": TOKEN_TABLE_RESERVE,
		"full_font_layout_bytes": total_full_font,
		"full_font_layout_sectors": math.ceil(total_full_font / SECTOR),
		"full_font_fits": total_full_font <= SIDECAR_BYTES,
		"subset_font_layout_bytes": total_subset_font,
		"subset_font_layout_sectors": math.ceil(total_subset_font / SECTOR),
		"subset_font_fits": total_subset_font <= SIDECAR_BYTES,
		"full_font_remaining_bytes": SIDECAR_BYTES - total_full_font,
		"subset_font_remaining_bytes": SIDECAR_BYTES - total_subset_font,
		"ram_warning": "Disk fit does not authorize resident loading; 150 sectors require 38 8-KiB banks.",
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	for key in ("translated_rows", "unique_strings", "deduplicated_string_bytes",
	            "string_pool_with_padding", "used_glyphs", "full_font_layout_bytes",
	            "full_font_layout_sectors", "full_font_fits", "full_font_remaining_bytes"):
		print(f"{key}: {result[key]}")
	print("output:", OUT)


if __name__ == "__main__":
	main()
