#!/usr/bin/env python3
"""Compare per-loader translation shards with free banks in each 96-sector RAM window."""

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
PRIMARY = ROOT / "translation" / "slot_topology.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "scene_shard_capacity.json"
SECTOR = 2048
BANK = 8192
WINDOW_BANKS = 24
HEADER = 64


def contains(entry, offset):
	start = entry["lba"] * SECTOR
	return start <= offset < start + entry["load_sectors"] * SECTOR


def shard_size(strings, glyph_count):
	position = HEADER
	for data in sorted(strings, key=len, reverse=True):
		inside = position % BANK
		if inside + len(data) > BANK:
			position += BANK - inside
		position += len(data)
	position = math.ceil(position / 32) * 32
	return position + glyph_count * 32 + glyph_count * 4


def main():
	char_map = json.loads(CHAR_MAP.read_text(encoding="utf-8"))
	rows = []
	with TSV.open(encoding="utf-8-sig", newline="") as source:
		for row in csv.DictReader(source, delimiter="\t"):
			text = row["번역"].strip()
			if text:
				rows.append((int(row["키(ISO오프셋)"], 16), text,
				             encode_string(text, char_map) + b"\x00"))

	primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	contexts = []
	seen = set()
	for owner, entries in (
		("primary", primary["logical_entries"]), ("overlay", overlay["entries"])):
		for entry in entries:
			if entry.get("physical_grid") is None:
				continue
			key = owner, entry["lba"], entry["load_sectors"]
			if key in seen:
				continue
			seen.add(key)
			matched = [(text, data) for offset, text, data in rows if contains(entry, offset)]
			if not matched:
				continue
			strings = {data for _, data in matched}
			glyphs = {ch for text, _ in matched for ch in text if ch in char_map}
			size = shard_size(strings, len(glyphs))
			used_banks = math.ceil(entry["load_sectors"] / 4)
			free_banks = WINDOW_BANKS - used_banks
			free_bytes = free_banks * BANK
			contexts.append({
				"owner": owner, "lba": entry["lba"], "load_sectors": entry["load_sectors"],
				"physical_grid": entry["physical_grid"], "translated_rows": len(matched),
				"unique_strings": len(strings), "glyphs": len(glyphs), "shard_bytes": size,
				"shard_sectors": math.ceil(size / SECTOR), "shard_banks": math.ceil(size / BANK),
				"free_whole_banks": free_banks, "free_bytes": free_bytes,
				"fits_free_banks": size <= free_bytes,
			})

	result = {
		"format": "SCENE-SHARD-CAPACITY",
		"policy": "Shard starts at the next whole 8-KiB bank after the original mode-6 load.",
		"contexts": contexts,
		"context_count": len(contexts),
		"fits_contexts": sum(x["fits_free_banks"] for x in contexts),
		"no_free_bank_contexts": sum(x["free_whole_banks"] == 0 for x in contexts),
		"max_shard_bytes": max(x["shard_bytes"] for x in contexts),
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("contexts:", result["context_count"])
	print("fits free banks:", result["fits_contexts"])
	print("does not fit:", result["context_count"] - result["fits_contexts"])
	print("no free bank:", result["no_free_bank_contexts"])
	print("max shard bytes:", result["max_shard_bytes"])
	print("output:", OUT)


if __name__ == "__main__":
	main()
