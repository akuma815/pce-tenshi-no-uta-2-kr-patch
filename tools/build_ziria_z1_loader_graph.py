#!/usr/bin/env python3
"""Build the read-only Z1 module catalogue and loader transition graph.

The tool consumes the original mixed-mode BIN plus already captured BizHawk
traces.  It never writes to the disc image; only JSON evidence is generated.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSLATION = ROOT / "translation"
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
OUT_CATALOG = TRANSLATION / "ziria_module_catalog.json"
OUT_GRAPH = TRANSLATION / "ziria_loader_graph.json"

DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
ENGINE_LBA = 258
ENGINE_SECTORS = 20
ENGINE_ISO_OFFSET = ENGINE_LBA * SECTOR
ENGINE_RUNTIME_BASE = 0x4000
OVERLAY_TABLE_ISO = 0x83531
OVERLAY_TABLE_RUNTIME = ENGINE_RUNTIME_BASE + OVERLAY_TABLE_ISO - ENGINE_ISO_OFFSET
OVERLAY_ENTRY_COUNT = 55
PRIMARY_TABLE_ISO = 0x424A5
PRIMARY_ENTRY_COUNT = 55
EXPECTED_BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"

TRACE_FILES = [
    "cd_read_trace.tsv",
    "task7_lba482_full_scene_trace.tsv",
    "task7_work_ram_long_trace.tsv",
    "task7_work_ram_tower_trace.tsv",
]

EVENT_RE = re.compile(
    r"^(?:CD_READ_ALL|CD_READ|TARGET_CD_READ)\s+.*?lba=(?P<lba>\d+)"
    r"\s+count=(?P<count>\d+)\s+dest_bank=(?P<dest>[0-9A-Fa-f]{2})"
    r"\s+mode=(?P<mode>[0-9A-Fa-f]{2})(?P<tail>.*)$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_track02(offset: int, length: int) -> bytes:
    with BIN.open("rb") as source:
        source.seek(DATA_TRACK_OFFSET + offset)
        data = source.read(length)
    if len(data) != length:
        raise EOFError(f"short Track02 read at 0x{offset:X}")
    return data


def parse_table(offset: int, count: int, base_lba: int, stride: int) -> list[dict]:
    raw = read_track02(offset, count * 4)
    entries = []
    for logical in range(count):
        record = raw[logical * 4:logical * 4 + 4]
        lba = (record[0] << 16) | (record[1] << 8) | record[2]
        sectors = record[3]
        delta = lba - base_lba
        grid = delta // stride if delta >= 0 and delta % stride == 0 else None
        entries.append({
            "logical_entry": logical,
            "lba": lba,
            "sector_count": sectors,
            "physical_grid": grid,
            "raw_hex": record.hex().upper(),
        })
    return entries


def parse_traces() -> tuple[list[dict], list[dict]]:
    observations = []
    sequences = []
    for name in TRACE_FILES:
        path = TRANSLATION / name
        if not path.exists():
            continue
        sequence = []
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            match = EVENT_RE.match(line)
            if not match:
                continue
            event = {
                "source": name,
                "lba": int(match.group("lba")),
                "sector_count": int(match.group("count")),
                "destination_bank": f"0x{match.group('dest').upper()}",
                "mode": f"0x{match.group('mode').upper()}",
            }
            frame = re.search(r"frame=(\d+)", line)
            return_pc = re.search(r"return_pc=([0-9A-Fa-f]{4})", match.group("tail"))
            if frame:
                event["frame"] = int(frame.group(1))
            if return_pc:
                event["return_pc"] = f"0x{return_pc.group(1).upper()}"
            observations.append(event)
            if not sequence or sequence[-1][0:2] != (event["lba"], event["sector_count"]):
                sequence.append((event["lba"], event["sector_count"]))
        if sequence:
            sequences.append({
                "source": name,
                "loads": [{"lba": lba, "sector_count": sectors} for lba, sectors in sequence],
            })
    return observations, sequences


def table_refs(entries: list[dict], lba: int) -> list[int]:
    return [x["logical_entry"] for x in entries if x["lba"] == lba]


def module(module_id: str, kind: str, lba: int | None, sectors: int | None,
           *, family: str, confidence: str, purpose: str, destination_bank: str | None = None,
           mode: str | None = None, physical_banks: str | None = None,
           runtime_range: str | None = None, entry_point: str | None = None,
           entry_status: str = "unknown", evidence: list[str] | None = None) -> dict:
    result = {
        "id": module_id,
        "module_kind": kind,
        "family": family,
        "purpose": purpose,
        "confidence": confidence,
        "lba": lba,
        "sector_count": sectors,
        "destination_bank": destination_bank,
        "cd_read_mode": mode,
        "physical_bank_interval": physical_banks,
        "runtime_range": runtime_range,
        "entry_point": entry_point,
        "entry_point_status": entry_status,
        "evidence": evidence or [],
    }
    return result


def main() -> None:
    actual_hash = sha256(BIN)
    if actual_hash != EXPECTED_BIN_SHA256:
        raise ValueError(f"original BIN hash mismatch: {actual_hash}")

    primary = parse_table(PRIMARY_TABLE_ISO, PRIMARY_ENTRY_COUNT, 162, 96)
    overlay = parse_table(OVERLAY_TABLE_ISO, OVERLAY_ENTRY_COUNT, 290, 96)
    observations, sequences = parse_traces()
    counts = Counter((x["lba"], x["sector_count"], x["destination_bank"], x["mode"])
                     for x in observations)
    sources = defaultdict(set)
    for item in observations:
        key = (item["lba"], item["sector_count"], item["destination_bank"], item["mode"])
        sources[key].add(item["source"])

    modules = [
        module("boot.kernel", "executable_engine", 2, 16, family="boot", confidence="runtime-high",
               purpose="System Card boot/opening program", destination_bank="0x00", mode="0x01",
               physical_banks="0x80-0x83", runtime_range="0x4000-0xBFFF",
               entry_point="0x600B", entry_status="header-jump-observed",
               evidence=["startup CD_READ trace", "first instruction is JMP $600B"]),
        module("boot.resource_a", "resource_bundle", 34, 12, family="boot", confidence="runtime-high",
               purpose="boot resource bundle", destination_bank="0x00", mode="0xFF",
               evidence=["startup CD_READ trace"]),
        module("opening.engine", "executable_engine", 98, 20, family="opening", confidence="runtime-high",
               purpose="opening/title program", destination_bank="0x00", mode="0x01",
               entry_point="0x5000", entry_status="header-jump-observed",
               evidence=["startup CD_READ trace", "first instruction is JMP $5000"]),
        module("opening.resource", "resource_bundle", 118, 6, family="opening", confidence="runtime-high",
               purpose="opening resource bundle", destination_bank="0x00", mode="0x01",
               evidence=["startup CD_READ trace"]),
        module("system.bundle", "resource_bundle", 226, 28, family="system", confidence="runtime-high",
               purpose="system/common bundle loaded before field engine", destination_bank="0x00", mode="0xFF",
               evidence=["startup CD_READ trace"]),
        module("field.main_engine", "executable_engine", 258, 20, family="field", confidence="static+runtime-high",
               purpose="field engine; owns overlay directory, loader routine, field GETFNT callsite",
               destination_bank="0x00", mode="0x01", physical_banks="0x80-0x84",
               runtime_range="0x4000-0xDFFF", entry_point="jump-table at 0x4000",
               entry_status="jump-table-observed",
               evidence=["CD_READ runtime trace", "GETFNT renderer catalogue", "overlay table at runtime $6531"]),
        module("field.resource", "resource_bundle", 278, 12, family="field", confidence="runtime-high/layout-inferred",
               purpose="field engine companion resource", destination_bank="0x00", mode="0x01",
               physical_banks="0x85-0x87 (inferred from following MPR snapshot)",
               evidence=["CD_READ runtime trace", "MPR2-4=85,86,87 after load"]),
        module("scene.field_start", "scene_package", 482, 96, family="field", confidence="runtime-high",
               purpose="starting field scene package; includes portrait-visible data in bank 0x6C",
               destination_bank="0x68", mode="0x06", physical_banks="0x68-0x7F",
               entry_status="data/package; no executable entry asserted",
               evidence=["full-scene and long-run traces", "bank 0x6C overwrite removed portrait"]),
        module("scene.battle_first", "scene_package", 290, 96, family="battle", confidence="runtime-route-high/semantic-medium",
               purpose="package loaded on first battle transition",
               destination_bank="0x68", mode="0x06", physical_banks="0x68-0x7F",
               entry_status="data/package; no executable entry asserted",
               evidence=["field→LBA290 transition in multiple traces", "user battle validation route"]),
        module("scene.tower_first", "scene_package", 2882, 96, family="tower/dungeon", confidence="runtime-route-high/semantic-high",
               purpose="first tower/dungeon scene package",
               destination_bank="0x68", mode="0x06", physical_banks="0x68-0x7F",
               entry_status="data/package; no executable entry asserted",
               evidence=["battle→LBA2882 transition in tower trace", "user tower validation route"]),
        module("subrenderer.memo", "subrenderer", None, None, family="menu/Memo", confidence="runtime-negative-load-high",
               purpose="Memo renderer entered without an intervening CD_READ; resident owner not yet split",
               entry_status="runtime PC not yet captured",
               evidence=["no CD_READ between field scene load and Memo entry"]),
        module("subrenderer.portrait", "subrenderer", None, None, family="portrait/event", confidence="runtime-high",
               purpose="portrait renderer; visible asset state depends on LBA482 bank 0x6C",
               entry_status="runtime PC not yet captured",
               evidence=["portrait control trace has no LBA3330 read", "bank 0x6C overwrite removes portrait"]),
    ]

    for item in modules:
        if item["lba"] is not None:
            item["primary_directory_entries"] = table_refs(primary, item["lba"])
            item["overlay_directory_entries"] = table_refs(overlay, item["lba"])
            item["track02_iso_range"] = (
                f"0x{item['lba'] * SECTOR:X}-0x{(item['lba'] + item['sector_count']) * SECTOR - 1:X}"
            )

    unique_reads = []
    for key, count in sorted(counts.items()):
        lba, sectors, dest, mode = key
        unique_reads.append({
            "lba": lba,
            "sector_count": sectors,
            "destination_bank": dest,
            "mode": mode,
            "observation_count": count,
            "trace_sources": sorted(sources[key]),
        })

    catalogue = {
        "format": "ZIRIA-Z1-MODULE-CATALOG",
        "version": 1,
        "status": "OBSERVED_ROUTE_PASS_WITH_EXPLICIT_UNRESOLVED_SUBRENDERER_ENTRY_POINTS",
        "source": {
            "bin": BIN.name,
            "sha256": actual_hash,
            "disc_mutated": False,
            "track02_data_offset_in_bin": DATA_TRACK_OFFSET,
        },
        "loader": {
            "owner_module": "field.main_engine",
            "overlay_table": {
                "track02_iso_offset": f"0x{OVERLAY_TABLE_ISO:X}",
                "runtime_address": f"0x{OVERLAY_TABLE_RUNTIME:04X}",
                "entry_count": OVERLAY_ENTRY_COUNT,
                "record_layout": ["lba_hi", "lba_mid", "lba_lo", "sector_count"],
            },
            "routine": {
                "runtime_range": "0x66DA-0x671D",
                "cd_read_callsite_runtime": "0x66FC",
                "bios_cd_read_entry": "0xE009",
                "return_pc": "0x66FF",
                "destination_mode_for_scene_packages": "0x06",
                "destination_bank_source": "RAM $22D0 (observed value 0x68)",
            },
        },
        "directories": {
            "primary": {"track02_iso_offset": f"0x{PRIMARY_TABLE_ISO:X}", "entries": primary},
            "overlay": {"track02_iso_offset": f"0x{OVERLAY_TABLE_ISO:X}", "entries": overlay},
        },
        "modules": modules,
        "runtime_unique_cd_reads": unique_reads,
        "unresolved": [
            "Memo runtime entry PC and exact resident owner",
            "portrait runtime entry PC; asset dependency on LBA482 bank 0x6C is proven",
            "96-sector packages are treated as scene packages, not executable modules, until a code entry is observed",
            "LBA3330 portrait-owner hypothesis is rejected because the targeted trace never read it",
        ],
    }

    graph = {
        "format": "ZIRIA-Z1-LOADER-GRAPH",
        "version": 1,
        "source_bin_sha256": actual_hash,
        "nodes": [
            {"id": x["id"], "kind": x["module_kind"], "family": x["family"], "lba": x["lba"]}
            for x in modules
        ],
        "edges": [
            {"from": "boot.kernel", "to": "opening.engine", "type": "observed_cd_load"},
            {"from": "opening.engine", "to": "field.main_engine", "type": "observed_cd_load"},
            {"from": "field.main_engine", "to": "scene.field_start", "type": "directory_load", "logical_entry": 2},
            {"from": "scene.field_start", "to": "subrenderer.memo", "type": "resident_call_no_cd_read"},
            {"from": "subrenderer.memo", "to": "scene.field_start", "type": "resident_return_no_cd_read"},
            {"from": "scene.field_start", "to": "subrenderer.portrait", "type": "resident_call_no_cd_read"},
            {"from": "subrenderer.portrait", "to": "scene.field_start", "type": "resident_return_no_cd_read"},
            {"from": "scene.field_start", "to": "scene.battle_first", "type": "directory_load", "logical_entry": 0},
            {"from": "scene.battle_first", "to": "scene.field_start", "type": "observed_return_route", "logical_entry": 2},
            {"from": "scene.battle_first", "to": "scene.tower_first", "type": "observed_tower_route", "logical_entry": 27},
        ],
        "observed_load_sequences": sequences,
        "ownership_rule": (
            "scene packages loaded to 0x68-0x7F replace the entire 192 KiB Super RAM window; "
            "no persistent hook, glyph cache, or state may be placed there across transitions"
        ),
    }

    OUT_CATALOG.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_GRAPH.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS original hash: {actual_hash}")
    print(f"modules: {len(modules)}")
    print(f"runtime unique reads: {len(unique_reads)}")
    print(f"overlay table runtime: 0x{OVERLAY_TABLE_RUNTIME:04X}")
    print(OUT_CATALOG)
    print(OUT_GRAPH)


if __name__ == "__main__":
    main()
