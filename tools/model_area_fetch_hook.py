#!/usr/bin/env python3
"""Reference model for the module-local translated-stream fetch hook.

This does not patch the ISO.  It applies the materialized area writes in memory and
executes every redirect through the proposed MPR3/continuation/token state machine.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
PLAN_PATH = ROOT / "translation" / "area_patch_plan_materialized.json"
OUT_PATH = ROOT / "translation" / "area_fetch_hook_model.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR_SIZE = 2048
AREA_SIZE = 96 * SECTOR_SIZE
BANK_SIZE = 8192
LOGICAL_BASE = 0x6000


def record_target(record: bytes) -> tuple[int, bool, int]:
	bank = record[1] & 0x7F
	token_mode = bool(record[1] & 0x80)
	logical = record[2] | record[3] << 8
	assert bank < 24 and LOGICAL_BASE <= logical <= 0x7FFF
	return bank, token_mode, bank * BANK_SIZE + logical - LOGICAL_BASE


def build_area_image(source, area, continuations):
	source.seek(DATA_TRACK_OFFSET + area["lba"] * SECTOR_SIZE)
	image = bytearray(source.read(AREA_SIZE))
	assert len(image) == AREA_SIZE
	for write in area["writes"]:
		start = write["area_relative_offset"]
		data = bytes.fromhex(write["data_hex"])
		assert 0 <= start <= AREA_SIZE - len(data)
		image[start:start + len(data)] = data
	for link in continuations:
		start = link["marker_area_offset"]
		data = bytes.fromhex(link["record_hex"])
		assert len(data) == 4 and start // BANK_SIZE == (start + 3) // BANK_SIZE
		image[start:start + 4] = data
	return image


def fetch_stream(image, start, token_mode, dictionary):
	ptr = start
	pending = None
	output = bytearray()
	links = tokens = reads = 0
	visited_links = set()
	while True:
		assert reads < AREA_SIZE * 2, "unterminated or cyclic translated stream"
		if pending is not None:
			value, pending = pending, None
		else:
			assert 0 <= ptr < AREA_SIZE
			value = image[ptr]
			ptr += 1
			reads += 1
			if value == 0x02:
				marker = ptr - 1
				assert marker not in visited_links, "continuation cycle"
				visited_links.add(marker)
				record = bytes((value, image[ptr], image[ptr + 1], image[ptr + 2]))
				bank, flag, ptr = record_target(record)
				assert not flag and ptr // BANK_SIZE == bank
				links += 1
				continue
			if token_mode and value in dictionary:
				first, pending = dictionary[value]
				value = first
				tokens += 1
		output.append(value)
		if value == 0:
			break
	return bytes(output), links, tokens, reads


def main():
	plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
	areas = {x["physical_grid"]: x for x in plan["area_writes"]}
	redirects = {}
	for item in plan["redirect_records"]:
		redirects.setdefault(item["physical_grid"], []).append(item)
	continuations = {}
	for item in plan["continuation_records"]:
		continuations.setdefault(item["physical_grid"], []).append(item)

	unique_streams = total_links = total_tokens = max_length = 0
	grid_stats = []
	with BIN.open("rb") as source:
		for grid, area in sorted(areas.items()):
			image = build_area_image(source, area, continuations.get(grid, []))
			dictionary = {
				int(token, 16): bytes.fromhex(sequence)
				for token, sequence in area["token_dictionary"].items()
			}
			assert all(len(x) == 2 for x in dictionary.values())
			seen = set()
			grid_links = grid_tokens = 0
			for redirect in redirects.get(grid, []):
				record = bytes.fromhex(redirect["record_hex"])
				bank, token_mode, start = record_target(record)
				assert start == redirect["target_area_offset"]
				assert token_mode == bool(dictionary)
				if start in seen:
					continue
				seen.add(start)
				stream, links, tokens, _ = fetch_stream(
					image, start, token_mode, dictionary)
				assert stream[-1] == 0 and 0x02 not in stream[:-1]
				max_length = max(max_length, len(stream))
				grid_links += links
				grid_tokens += tokens
			unique_streams += len(seen)
			total_links += grid_links
			total_tokens += grid_tokens
			grid_stats.append({
				"physical_grid": grid,
				"redirects": len(redirects.get(grid, [])),
				"unique_streams": len(seen),
				"continuations_traversed": grid_links,
				"tokens_expanded": grid_tokens,
			})

	output = {
		"format": "AREA-FETCH-HOOK-MODEL",
		"version": 1,
		"abi": {
			"redirect": "01, flags|bank_index, logical_low, logical_high, 00",
			"continuation": "02, bank_index, logical_low, logical_high",
			"token_mode_flag": "0x80 in redirect bank byte",
			"physical_bank": "[$22D0] + (bank_byte & 0x7F)",
			"mapped_window": "MPR3 $6000..$7FFF",
			"mpr_rule": "TMA #$08 before every mapped read; TAM #$08 restore on every path",
			"state_rule": "state lives in verified module-local padding; $55/$56 are only borrowed during one call",
		},
		"stats": {
			"redirects_executed": sum(len(x) for x in redirects.values()),
			"unique_streams": unique_streams,
			"continuations_traversed_once_per_unique_stream": total_links,
			"tokens_expanded_once_per_unique_stream": total_tokens,
			"maximum_expanded_stream_bytes": max_length,
		},
		"grids": grid_stats,
	}
	OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
	print(json.dumps(output["stats"], indent=2))
	print("model verification: OK")
	print("output:", OUT_PATH)


if __name__ == "__main__":
	main()
