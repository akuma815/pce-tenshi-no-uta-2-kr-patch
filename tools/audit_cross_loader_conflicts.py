#!/usr/bin/env python3
"""Reject primary package writes that overlap second-engine overlay live ranges."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "translation" / "area_patch_plan_materialized.json"
OVERLAY = ROOT / "translation" / "overlay_topology.json"
OUT = ROOT / "translation" / "cross_loader_conflicts.json"
SECTOR = 2048


def find_conflicts():
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
	ranges = [
		(x["logical_entry"], x["lba"] * SECTOR,
		 (x["lba"] + x["load_sectors"]) * SECTOR)
		for x in overlay["entries"]
	]
	conflicts = []
	for area in plan["area_writes"]:
		for write in area["writes"]:
			start = area["lba"] * SECTOR + write["area_relative_offset"]
			end = start + write["length"]
			hits = sorted({logical for logical, left, right in ranges
			               if start < right and end > left})
			if hits:
				conflicts.append({
					"primary_grid": area["physical_grid"], "kind": write["kind"],
					"start": start, "end": end, "overlay_logical_entries": hits,
				})
	return conflicts


def main():
	conflicts = find_conflicts()
	result = {
		"format": "CROSS-LOADER-CONFLICT-AUDIT",
		"safe": not conflicts,
		"conflict_count": len(conflicts),
		"affected_primary_grids": sorted({x["primary_grid"] for x in conflicts}),
		"conflicts": conflicts,
	}
	OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print("cross-loader conflicts:", len(conflicts))
	print("affected primary grids:", len(result["affected_primary_grids"]))
	print("safe:", result["safe"])
	print("output:", OUT)
	return 1 if conflicts else 0


if __name__ == "__main__":
	raise SystemExit(main())
