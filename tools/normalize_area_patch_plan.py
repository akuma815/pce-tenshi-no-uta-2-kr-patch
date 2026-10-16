# -*- coding: utf-8 -*-
"""Normalize all 30 mapped-area layouts into one symbolic KAPLAN1 patch plan."""
from __future__ import annotations

import json
import os
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY = GAME_DIR / "translation" / "slot_topology.json"
KAP_DIR = GAME_DIR / "translation" / "mapped_area_packages"
HOLE_DIR = GAME_DIR / "translation" / "overflow_area_hole_layouts"
CHAIN_DIR = GAME_DIR / "translation" / "fragmented_area_chains"
OUT_PATH = GAME_DIR / "translation" / "area_patch_plan.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_contiguous(manifest_path):
    manifest = read_json(manifest_path)
    blob_path = Path(manifest_path).with_suffix(".bin")
    blob = blob_path.read_bytes()
    return {
        "physical_grid": manifest["physical_grid"],
        "layout": "contiguous",
        "lba": manifest["lba"],
        "logical_entries": manifest["logical_entries"],
        "original_load_sectors": manifest["original_load_sectors"],
        "patched_load_sectors": manifest["needed_sectors"],
        "writes": [{
            "kind": "kap1_blob",
            "area_relative_offset": manifest["package_area_offset"],
            "data_hex": blob.hex(),
            "length": len(blob),
        }],
        "redirects": {
            source: {"area_relative_target": value["area_relative_offset"]}
            for source, value in manifest["source_redirects"].items()
        },
        "continuations": [],
        "token_dictionary": {},
    }


def normalize_holes(path):
    source = read_json(path)
    return {
        "physical_grid": source["physical_grid"],
        "layout": "holes",
        "lba": source["lba"],
        "logical_entries": source["logical_entries"],
        "original_load_sectors": source["original_load_sectors"],
        "patched_load_sectors": source["extended_load_sectors"],
        "writes": [{
            "kind": "string",
            "area_relative_offset": item["area_relative_offset"],
            "data_hex": item["data_hex"],
            "length": item["length"],
        } for item in source["placements"]],
        "redirects": source["redirects"],
        "continuations": [],
        "token_dictionary": {},
    }


def normalize_chains(path, tokenized=False):
    source = read_json(path)
    writes = []
    continuations = []
    redirect_key = "redirects"
    for chain_index, chain in enumerate(source["chains"]):
        segments = chain["segments"]
        for segment_index, segment in enumerate(segments):
            writes.append({
                "kind": "token_segment" if tokenized else "string_segment",
                "area_relative_offset": segment["area_relative_offset"],
                "data_hex": segment["data_hex"],
                "length": segment["data_length"],
            })
            if not segment["final"]:
                target = segments[segment_index + 1]["area_relative_offset"]
                continuations.append({
                    "marker": "02",
                    "marker_area_offset": segment["area_relative_offset"] + segment["data_length"],
                    "target_area_offset": target,
                    "chain_index": chain_index,
                })
    return {
        "physical_grid": source["physical_grid"],
        "layout": "token_chains" if tokenized else "chains",
        "lba": source["lba"],
        "logical_entries": source["logical_entries"],
        "original_load_sectors": source["original_load_sectors"],
        "patched_load_sectors": source["extended_load_sectors"],
        "writes": writes,
        "redirects": source[redirect_key],
        "continuations": continuations,
        "token_dictionary": source.get("token_dictionary", {}),
    }


def validate_area(area):
    spans = []
    for write in area["writes"]:
        data = bytes.fromhex(write["data_hex"])
        if len(data) != write["length"]:
            raise ValueError(f"grid{area['physical_grid']:02d}: write length mismatch")
        start = write["area_relative_offset"]
        end = start + len(data)
        if not (0 <= start < end <= 96 * 2048):
            raise ValueError(f"grid{area['physical_grid']:02d}: write outside area")
        spans.append((start, end, write["kind"]))
    for continuation in area["continuations"]:
        start = continuation["marker_area_offset"]
        end = start + 4
        if not (0 <= start < end <= 96 * 2048):
            raise ValueError(f"grid{area['physical_grid']:02d}: continuation outside area")
        spans.append((start, end, "continuation"))
    spans.sort()
    for left, right in zip(spans, spans[1:]):
        if left[1] > right[0]:
            raise ValueError(f"grid{area['physical_grid']:02d}: overlapping writes {left} {right}")
    if not (area["original_load_sectors"] <= area["patched_load_sectors"] <= 96):
        raise ValueError(f"grid{area['physical_grid']:02d}: invalid load sector count")
    for target in area["redirects"].values():
        value = target["area_relative_target"]
        if not 0 <= value < 96 * 2048:
            raise ValueError(f"grid{area['physical_grid']:02d}: redirect target outside area")


def main():
    topology = read_json(TOPOLOGY)
    expected = {
        item["grid"] for item in topology["physical_grids"]
        if item["logical_entries"] and item["translated_rows"]
    }
    areas = []
    for path in sorted(KAP_DIR.glob("grid*_area_strings.json")):
        areas.append(normalize_contiguous(path))
    areas.append(normalize_holes(HOLE_DIR / "grid41_hole_layout.json"))
    areas.append(normalize_chains(CHAIN_DIR / "grid28_chains.json"))
    areas.append(normalize_chains(CHAIN_DIR / "grid40_chains.json"))
    areas.append(normalize_chains(CHAIN_DIR / "grid15_token_chains.json", tokenized=True))
    areas.sort(key=lambda x: x["physical_grid"])

    actual = [area["physical_grid"] for area in areas]
    if len(actual) != len(set(actual)):
        raise ValueError("duplicate physical grids in normalized plan")
    if set(actual) != expected:
        raise ValueError(f"grid coverage mismatch: missing={sorted(expected-set(actual))}, extra={sorted(set(actual)-expected)}")
    for area in areas:
        validate_area(area)

    plan = {
        "format": "KAPLAN1",
        "version": 1,
        "symbolic_link_encoding": {
            "redirect": "01, target bank/address (not materialized until fetch ABI is finalized)",
            "continuation": "02, target area-relative address (symbolic in this plan)",
        },
        "area_count": len(areas),
        "areas": areas,
    }
    OUT_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"KAPLAN1 normalized: {len(areas)} areas")
    for layout in ("contiguous", "holes", "chains", "token_chains"):
        print(f"  {layout}: {sum(a['layout']==layout for a in areas)}")
    print("output:", OUT_PATH)


if __name__ == "__main__":
    main()
