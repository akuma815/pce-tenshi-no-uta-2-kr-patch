#!/usr/bin/env python3
"""Conservative static liveness audit of the field engine $4000 API table.

Area blocks mix code and data.  Any raw address occurrence is therefore treated as live;
zero-reference entries are only candidates for later dynamic validation, never proof.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
PLAN = ROOT / "translation" / "area_patch_plan_materialized.json"
OUT = ROOT / "translation" / "field_api_liveness.json"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
AREA_SIZE = 96 * SECTOR
ENGINE_ISO = 0x41000
MPR2_SIZE = 8192


def occurrences(data, needle):
	start = 0
	result = []
	while True:
		start = data.find(needle, start)
		if start < 0:
			return result
		result.append(start)
		start += 1


def main():
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + ENGINE_ISO)
		engine = source.read(MPR2_SIZE)
		areas = {}
		for area in plan["area_writes"]:
			source.seek(DATA_TRACK_OFFSET + area["lba"] * SECTOR)
			areas[area["physical_grid"]] = source.read(AREA_SIZE)

	entries = []
	targets = []
	for offset in range(0, 0x48, 3):
		targets.append(engine[offset + 1] | engine[offset + 2] << 8)
	unique_targets = sorted(set(targets))
	for offset in range(0, 0x48, 3):
		assert engine[offset] == 0x4C
		entry = 0x4000 + offset
		target = engine[offset + 1] | engine[offset + 2] << 8
		address = bytes((entry & 0xFF, entry >> 8))
		opcoded = bytes((0x20,)) + address
		jumped = bytes((0x4C,)) + address
		per_grid = []
		raw_total = jsr_total = jmp_total = 0
		for grid, data in sorted(areas.items()):
			raw = len(occurrences(data, address))
			jsr = len(occurrences(data, opcoded))
			jmp = len(occurrences(data, jumped))
			if raw:
				per_grid.append({"physical_grid": grid, "raw_words": raw,
				                 "jsr_patterns": jsr, "jmp_patterns": jmp})
			raw_total += raw
			jsr_total += jsr
			jmp_total += jmp
		engine_raw = len(occurrences(engine[0x48:], address))
		pattern_live = bool(jsr_total or jmp_total or engine_raw)
		if target in unique_targets and unique_targets.index(target) + 1 < len(unique_targets):
			nominal_span = unique_targets[unique_targets.index(target) + 1] - target
		else:
			nominal_span = None
		entries.append({
			"entry": f"0x{entry:04X}",
			"target": f"0x{target:04X}",
			"area_raw_words": raw_total,
			"area_jsr_patterns": jsr_total,
			"area_jmp_patterns": jmp_total,
			"engine_raw_words_excluding_table": engine_raw,
			"referenced_grids": per_grid,
			"nominal_span_to_next_api_target": nominal_span,
			"classification": "static-live" if pattern_live else "raw-only-dynamic-validation-candidate",
		})

	candidates = [x for x in entries if x["classification"] == "raw-only-dynamic-validation-candidate"]
	live_targets = {x["target"] for x in entries if x["classification"] == "static-live"}
	unique_candidate_spans = {}
	for item in candidates:
		if item["target"] not in live_targets and item["nominal_span_to_next_api_target"] is not None:
			unique_candidate_spans[item["target"]] = item["nominal_span_to_next_api_target"]
	result = {
		"format": "FIELD-API-LIVENESS",
		"version": 1,
		"method": "Conservative unaligned raw-word plus JSR/JMP pattern scan over 30 physical area grids and field MPR2.",
		"limitations": [
			"Raw matches may be data and therefore false positives.",
			"Computed/stack-dispatched calls may have no literal entry address.",
			"A zero-reference result requires emulator execution coverage before reclamation.",
		],
		"entries": entries,
		"dynamic_validation_candidates": [x["entry"] for x in candidates],
		"candidate_unique_target_spans": unique_candidate_spans,
		"maximum_candidate_bytes_after_dynamic_proof": sum(unique_candidate_spans.values()),
		"reclaimable_now": [],
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("API entries:", len(entries))
	print("static-live:", len(entries) - len(candidates))
	print("dynamic-validation candidates:", len(candidates))
	print("candidates:", ", ".join(x["entry"] for x in candidates) or "none")
	print("maximum bytes after dynamic proof:", sum(unique_candidate_spans.values()))
	print("reclaimable now: NONE")
	print("output:", OUT)


if __name__ == "__main__":
	main()
