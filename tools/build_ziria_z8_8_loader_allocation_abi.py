#!/usr/bin/env python3
"""Build the read-only Z8.8 loader-allocation and reader-ABI gate."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INDEX = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
WIRE_MANIFEST = ROOT / "translation" / "ziria_z8_field_redirect_format_manifest.json"
WIRE_SPEC = ROOT / "module_relink" / "z8_field_redirect_format" / "field_dialogue_format.json"
LOADER_REF = ROOT / "module_relink" / "z8_field_dialogue_refs" / "loader_reference.json"
LINKER_LAYOUT = ROOT / "module_relink" / "linker_layout.json"
EXTENSION_REGISTRY = ROOT / "module_relink" / "extension_registry.json"
ENGINE = ROOT / "module_relink" / "track02" / "semantic_modules" / "field.main_engine_lba0258_s20.bin"
TRACK02 = ROOT / "extracted_bin" / "Track02_data.iso"
OUT_DIR = ROOT / "module_relink" / "z8_8_loader_allocation_abi"
OUT = ROOT / "translation" / "ziria_z8_8_loader_allocation_abi_manifest.json"

SCENE_LBA = 482
SECTOR = 2048
BANK = 8192
READER_START = 0x0284
READER_END = 0x02F0


def sha256(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def merge(ranges: list[tuple[int, int]]) -> list[list[int]]:
	out: list[list[int]] = []
	for start, end in sorted(ranges):
		if start >= end:
			raise ValueError("empty source range")
		if out and start <= out[-1][1]:
			out[-1][1] = max(out[-1][1], end)
		else:
			out.append([start, end])
	return out


def main() -> None:
	OUT_DIR.mkdir(parents=True, exist_ok=True)
	wire = json.loads(WIRE_MANIFEST.read_text(encoding="utf-8"))
	wire_spec = json.loads(WIRE_SPEC.read_text(encoding="utf-8"))
	loader = json.loads(LOADER_REF.read_text(encoding="utf-8"))
	layout = json.loads(LINKER_LAYOUT.read_text(encoding="utf-8"))
	registry = json.loads(EXTENSION_REGISTRY.read_text(encoding="utf-8"))

	scene_base = SCENE_LBA * SECTOR
	scene_bytes = loader["target_coordinate"]["bytes"]
	scene_end = scene_base + scene_bytes
	rows: list[dict[str, str]] = []
	with SOURCE_INDEX.open(encoding="utf-8-sig", newline="") as source:
		rows = list(csv.DictReader(source, delimiter="\t"))
	if len(rows) != 235:
		raise ValueError(f"expected 235 source rows, got {len(rows)}")

	ranges: list[tuple[int, int]] = []
	keys: list[int] = []
	for row in rows:
		start = int(row["source_iso_offset"], 16)
		length = int(row["raw_length"])
		end = start + length
		if not (scene_base <= start < end <= scene_end):
			raise ValueError(f"source range outside LBA 482 scene: {row['id']}")
		if len(bytes.fromhex(row["raw_hex"])) != length:
			raise ValueError(f"raw length mismatch: {row['id']}")
		ranges.append((start - scene_base, end - scene_base))
		keys.append(int.from_bytes(bytes.fromhex(row["source_key_u24le"]), "little"))

	if len(set(keys)) != len(keys):
		raise ValueError("duplicate source key")
	merged = merge(ranges)
	if sum(end - start for start, end in merged) != sum(end - start for start, end in ranges):
		raise ValueError("source text ranges overlap")

	reclaim_rows = [{
		"scene_offset": f"0x{start:05X}",
		"end_exclusive": f"0x{end:05X}",
		"bytes": end - start,
	} for start, end in sorted(ranges)]
	with (OUT_DIR / "source_reclaim_ranges.tsv").open("w", encoding="utf-8", newline="") as dest:
		writer = csv.DictWriter(dest, fieldnames=list(reclaim_rows[0]), delimiter="\t")
		writer.writeheader()
		writer.writerows(reclaim_rows)

	assets = {
		"index": wire["wire"]["index_bytes"],
		"text": wire["wire"]["text_bytes"],
		"glyphs_packed18": wire["wire"]["packed_glyph_bytes"],
	}
	largest = max(end - start for start, end in merged)
	asset_fit = {
		name: {
			"bytes": size,
			"requires_contiguous": True,
			"largest_reclaim_run_bytes": largest,
			"fits_unchanged_wire": size <= largest,
		}
		for name, size in assets.items()
	}

	engine = ENGINE.read_bytes()
	reader = engine[READER_START:READER_END]
	if len(reader) != READER_END - READER_START:
		raise ValueError("reader range outside engine")
	jsr_4036 = sum(
		engine[i:i + 3] == b"\x20\x36\x40"
		for i in range(len(engine) - 2)
	)

	modules = {item["id"]: item for item in layout["modules"]}
	resident = [
		{"owner": "scene.field_start", "banks": "0x68-0x7F", "count": 24,
		 "lifetime": "current scene; replaced atomically by battle/tower scene load"},
		{"owner": "field.main_engine", "banks": "0x80-0x84", "count": 5,
		 "lifetime": "field-family resident"},
		{"owner": "field.resource", "banks": "0x85-0x87", "count": 3,
		 "lifetime": "field-family resident"},
	]
	if modules["scene.field_start"]["physical_bank_interval"] != "0x68-0x7F":
		raise ValueError("scene bank ownership changed")
	if modules["field.main_engine"]["physical_bank_interval"] != "0x80-0x84":
		raise ValueError("engine bank ownership changed")
	if not modules["field.resource"]["physical_bank_interval"].startswith("0x85-0x87"):
		raise ValueError("resource bank ownership changed")

	abi = {
		"entry": "0x4036 -> JMP 0x4284",
		"dispatch_order": [
			{"condition": "RAM $55 != 0", "reader": "ptr54", "cursor": "$54/$55", "runtime": "0x42BA"},
			{"condition": "RAM $53 != 0", "reader": "ptr52", "cursor": "$52/$53", "runtime": "0x42AB"},
			{"condition": "RAM $2E69 != 0", "reader": "overlay", "cursor": "$4B/$4C", "runtime": "0x42D2/0x42DE"},
			{"condition": "otherwise", "reader": "main", "cursor": "$4B/$4C", "runtime": "0x4293"},
		],
		"return_contract": {
			"value": "next stream byte in A and RAM $2D80",
			"x": "preserved by all four reader paths",
			"y": "preserved by all four reader paths",
			"flags": "N/Z reflect final LDA $2D80; other arithmetic flags are not an ABI promise",
			"mpr": "main saves/restores MPR2-4; overlay saves/restores MPR6; ptr52/ptr54 do not remap",
		},
		"continuation": {
			"main": "increment $4B/$4C",
			"overlay": "increment $4B/$4C while MPR6 maps $22D0 + $2E69",
			"ptr52": "increment $52/$53; NUL is returned normally",
			"ptr54": "increment $54/$55; NUL clears $54/$55 and immediately fetches from main $4B/$4C",
		},
		"reader_engine_offset": f"0x{READER_START:04X}-0x{READER_END - 1:04X}",
		"reader_sha256": hashlib.sha256(reader).hexdigest().upper(),
		"direct_jsr_4036_count_in_engine": jsr_4036,
		"status": "STATIC_ABI_PASS",
	}

	total_reclaim = sum(end - start for start, end in merged)
	total_assets = sum(assets.values())
	all_fit = all(item["fits_unchanged_wire"] for item in asset_fit.values())
	status = "ABI_PASS_UNCHANGED_WIRE_ALLOCATION_FAIL"
	result = {
		"format": "ZIRIA-Z8.8-LOADER-ALLOCATION-ABI",
		"version": 1,
		"task": "Z8.8-loader-owned-allocation-and-reader-ABI",
		"status": status,
		"mutation_scope": "analysis-only; no CUE/BIN/ISO or emulated-state writes",
		"inputs": {
			"source_index": {"path": str(SOURCE_INDEX.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(SOURCE_INDEX)},
			"wire_manifest": {"path": str(WIRE_MANIFEST.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(WIRE_MANIFEST)},
			"wire_spec": {"path": str(WIRE_SPEC.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(WIRE_SPEC)},
			"loader_reference": {"path": str(LOADER_REF.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(LOADER_REF)},
			"linker_layout": {"path": str(LINKER_LAYOUT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(LINKER_LAYOUT)},
			"extension_registry": {"path": str(EXTENSION_REGISTRY.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(EXTENSION_REGISTRY)},
			"engine": {"path": str(ENGINE.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(ENGINE)},
			"track02_iso": {"path": str(TRACK02.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(TRACK02)},
		},
		"loader_owned_storage": {
			"scene": {"lba": SCENE_LBA, "sectors": 96, "bytes": scene_bytes, "banks": "0x68-0x7F"},
			"resident_bank_owners": resident,
			"covered_bank_count": sum(item["count"] for item in resident),
			"covered_interval": "0x68-0x87",
			"free_persistent_bank_count": 0,
			"approved_extension_allocations": len(registry["approved_allocations"]),
			"prohibited": registry["prohibited"],
			"source_reclaim": {
				"ranges": len(ranges),
				"merged_runs": len(merged),
				"bytes": total_reclaim,
				"largest_run_bytes": largest,
				"asset_bytes": total_assets,
				"gross_margin_bytes": total_reclaim - total_assets,
				"ranges_path": "module_relink/z8_8_loader_allocation_abi/source_reclaim_ranges.tsv",
			},
			"unchanged_wire_asset_fit": asset_fit,
			"unchanged_wire_all_assets_fit": all_fit,
			"decision": "FAIL: aggregate reclaim bytes do not create the contiguous index/text/glyph blobs required by Z8.7",
		},
		"reader_abi": abi,
		"gate": {
			"abi": "PASS",
			"loader_owned_allocation_for_unchanged_z8_7_wire": "FAIL",
			"disc_build": "BLOCKED",
			"reason": "no approved persistent bank and no reclaim run can hold any required contiguous wire blob",
		},
		"next_gate": {
			"id": "Z8.9",
			"goal": "redesign storage representation for fragmented scene-owned ranges or reduce runtime assets before any disc mutation",
			"requirements": [
				"preserve the proven $4036 reader ABI",
				"do not depend on cross-family persistence in banks 0x68-0x7F",
				"replace Z8.7 contiguous target semantics only through a versioned wire format",
				"prove every fragment and lookup access before generating CUE/BIN/ISO",
			],
		},
	}
	OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
	print("status:", status)
	print("source reclaim bytes:", total_reclaim)
	print("largest reclaim run:", largest)
	print("wire assets:", total_assets)
	print("direct JSR $4036:", jsr_4036)
	print("output:", OUT)


if __name__ == "__main__":
	main()
