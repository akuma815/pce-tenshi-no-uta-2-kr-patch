#!/usr/bin/env python3
"""Build and offline-replay the read-only Z8.3 field source-key probe."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_MANIFEST = ROOT / "translation" / "ziria_z8_field_dialogue_reference_manifest.json"
CATALOG = ROOT / "module_relink" / "z8_field_dialogue_refs" / "field_dialogue_reference_catalog.csv"
TRACE = ROOT / "translation" / "ziria_z6_stream_source_trace.tsv"
LUA = ROOT / "tools" / "trace_ziria_z8_field_source_keys.lua"
LOOKUP = ROOT / "translation" / "ziria_z8_field_source_key_lookup.tsv"
REPLAY = ROOT / "translation" / "ziria_z8_field_source_key_offline_replay.tsv"
MANIFEST = ROOT / "translation" / "ziria_z8_field_source_key_probe_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_3_field_source_key_probe.md"

MODULE_START = 482 * 2048
FIELD_LBA = 482
FIELD_COUNT = 96
BANK_BASE = 0x68


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path, delimiter: str = ",") -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=delimiter))


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    for path in (REFERENCE_MANIFEST, CATALOG, TRACE, LUA):
        if not path.is_file():
            raise FileNotFoundError(path)
    reference = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    if reference["status"] != "LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN":
        raise ValueError("reference catalogue status")
    if sha256(CATALOG) != reference["outputs"]["reference_catalog_sha256"]:
        raise ValueError("reference catalogue hash")

    catalog_rows = read_csv(CATALOG)
    if len(catalog_rows) != 236:
        raise ValueError("reference catalogue population")
    by_key = {}
    ranges = []
    lookup_rows = []
    for row in catalog_rows:
        relative = int(row["source_module_offset"], 16)
        key = f"{relative:06X}"
        if key in by_key:
            raise ValueError(f"duplicate source key: {key}")
        by_key[key] = row
        source = int(row["source_iso_offset"], 16)
        ranges.append((source, source + int(row["raw_length"]), row))
        lookup_rows.append({
            "source_key": key,
            "id": row["id"],
            "source_iso_offset": row["source_iso_offset"],
            "raw_length": row["raw_length"],
        })
    write_tsv(
        LOOKUP,
        ["source_key", "id", "source_iso_offset", "raw_length"],
        lookup_rows,
    )

    trace_rows = read_csv(TRACE, "\t")
    replay_rows = []
    key_mismatches = 0
    iso_mismatches = 0
    exact_ids = set()
    containing_ids = set()
    scene_stream_rows = 0
    for trace in trace_rows:
        if trace.get("event") != "STREAM":
            continue
        if trace.get("last_lba") != str(FIELD_LBA):
            continue
        mpr = int(trace["mpr"], 16)
        if not BANK_BASE <= mpr <= 0x7F:
            continue
        logical = int(trace["logical"], 16)
        relative = (mpr - BANK_BASE) * 0x2000 + (logical & 0x1FFF)
        key = f"{relative:06X}"
        overlay = int(trace["overlay_offset"], 16)
        iso_offset = int(trace["iso_offset"], 16)
        key_match = relative == overlay
        iso_match = MODULE_START + relative == iso_offset
        if not key_match:
            key_mismatches += 1
        if not iso_match:
            iso_mismatches += 1
        exact = by_key.get(key)
        containing = next(
            (row for start, end, row in ranges if start <= iso_offset < end),
            None,
        )
        if exact:
            event = "START_HIT"
            exact_ids.add(exact["id"])
        elif containing:
            event = "INTERIOR_HIT"
        else:
            event = "NONCATALOG_STREAM"
        if containing:
            containing_ids.add(containing["id"])
        replay_rows.append({
            "frame": trace["frame"],
            "event": event,
            "reader": trace["reader"],
            "logical": trace["logical"],
            "page": trace["page"],
            "mpr": trace["mpr"],
            "source_key": key,
            "catalog_id": exact["id"] if exact else "-",
            "containing_record_id": containing["id"] if containing else "-",
            "trace_overlay_offset": trace["overlay_offset"],
            "trace_iso_offset": trace["iso_offset"],
            "key_matches_trace_overlay": "yes" if key_match else "no",
            "key_matches_trace_iso": "yes" if iso_match else "no",
        })
        scene_stream_rows += 1
    if not replay_rows:
        raise ValueError("no replay rows")
    write_tsv(REPLAY, list(replay_rows[0].keys()), replay_rows)

    lua_text = LUA.read_text(encoding="utf-8")
    forbidden = [
        "memory.write", "mainmemory.write", "joypad.set", "savestate.load",
        "emu.setregister", "client.openrom", "event.on_bus_write",
    ]
    forbidden_hits = [token for token in forbidden if token in lua_text]
    if forbidden_hits:
        raise ValueError(f"write-capable Lua APIs found: {forbidden_hits}")
    required_hooks = ["0x4293", "0x42DE", "0x42AB", "0x42BA", "0xE009"]
    missing_hooks = [hook for hook in required_hooks if hook not in lua_text]
    if missing_hooks:
        raise ValueError(f"missing Lua hooks: {missing_hooks}")

    manifest = {
        "format": "ZIRIA-Z8-FIELD-SOURCE-KEY-PROBE",
        "version": 1,
        "task": "Z8-v3-read-only-source-key-probe",
        "status": "OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING",
        "mutation_scope": "host logs only; no emulated memory/controller/state/disc writes",
        "inputs": {
            "reference_manifest": {
                "path": REFERENCE_MANIFEST.relative_to(ROOT).as_posix(),
                "sha256": sha256(REFERENCE_MANIFEST),
            },
            "reference_catalog": {
                "path": CATALOG.relative_to(ROOT).as_posix(),
                "sha256": sha256(CATALOG),
            },
            "prior_runtime_trace": {
                "path": TRACE.relative_to(ROOT).as_posix(),
                "sha256": sha256(TRACE),
            },
            "lua_probe": {
                "path": LUA.relative_to(ROOT).as_posix(),
                "sha256": sha256(LUA),
            },
        },
        "lookup": {
            "rows": len(lookup_rows),
            "key_basis": "scene-relative offset formatted as canonical six-digit hex",
            "key_width_bits": 24,
            "unique": len(by_key) == len(lookup_rows),
            "path": LOOKUP.relative_to(ROOT).as_posix(),
            "sha256": sha256(LOOKUP),
        },
        "offline_replay": {
            "scene_stream_rows": scene_stream_rows,
            "key_mismatches": key_mismatches,
            "iso_mismatches": iso_mismatches,
            "unique_exact_start_hits": len(exact_ids),
            "unique_containing_record_hits": len(containing_ids),
            "exact_start_ids": sorted(exact_ids),
            "containing_record_ids": sorted(containing_ids),
            "path": REPLAY.relative_to(ROOT).as_posix(),
            "sha256": sha256(REPLAY),
            "status": "PASS" if key_mismatches == 0 and iso_mismatches == 0 else "FAIL",
        },
        "lua_static_audit": {
            "forbidden_write_api_hits": forbidden_hits,
            "required_exec_hooks": required_hooks,
            "missing_hooks": missing_hooks,
            "initial_scene_identity": "manual_field_visible_assumption",
            "identity_refresh": "next mode-06 CD read observed at BIOS entry 0xE009",
            "writes": "host TSV/status files only",
        },
        "runtime_gate": {
            "status": "PENDING",
            "setup": "open Lua manually only after the first field is visible",
            "pass": [
                "runtime status remains running/closed without emulator crash",
                "lookup_count=236",
                "START_HIT records use catalogue IDs and canonical source keys",
                "after any mode-06 load, scene_identity_source=observed_mode06_cd_read",
                "no game-state or rendering regression while probe is attached",
            ],
            "not_proved_by_offline_replay": (
                "complete 236-record consumer denominator, redirect storage, hook ABI, "
                "or loader-owned translation lifetime"
            ),
        },
        "outputs": {
            "lookup": LOOKUP.relative_to(ROOT).as_posix(),
            "offline_replay": REPLAY.relative_to(ROOT).as_posix(),
            "report": REPORT.relative_to(ROOT).as_posix(),
        },
    }
    if manifest["offline_replay"]["status"] != "PASS":
        raise ValueError("offline replay mismatch")
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    REPORT.write_text(
        f"""# Z8.3 field source-key read-only probe

## 정적/오프라인 판정

- lookup: **{len(lookup_rows)}개**, 24-bit scene-relative key 중복 0
- 기존 Z6 trace의 field scene stream read: **{scene_stream_rows}회**
- 계산 key와 trace overlay offset 불일치: **{key_mismatches}건**
- 계산 key와 Track02 ISO offset 불일치: **{iso_mismatches}건**
- 정확한 레코드 시작 hit: **{len(exact_ids)}개**
- 레코드 내부까지 포함한 관측: **{len(containing_ids)}개**
- Lua write-capable API 검출: **0건**

상태는 `OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING`이다. 기존 trace로 source-key
수식은 검증됐지만, 새 Lua가 현재 BizHawk 실행에서 정상 동작하는지는 별도
runtime 증거가 필요하다.

## 실행 절차

1. Lua 없이 게임을 실행해 첫 필드가 보일 때까지 진행한다.
2. BizHawk Lua Console에서 `tools/trace_ziria_z8_field_source_keys.lua`를 연다.
3. 첫 대화, Memo 진입·복귀, 첫 전투·필드 복귀, 탑 진입까지 진행한다.
4. `translation/ziria_z8_field_source_key_runtime_status.txt`와
   `translation/ziria_z8_field_source_key_runtime_trace.tsv`를 보존한다.

이 probe는 host 로그만 쓰며 게임 메모리, 입력, savestate, CUE/BIN/ISO를
수정하지 않는다.
""",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": manifest["status"],
        "lookup_rows": len(lookup_rows),
        "scene_stream_rows": scene_stream_rows,
        "key_mismatches": key_mismatches,
        "iso_mismatches": iso_mismatches,
        "unique_exact_start_hits": len(exact_ids),
        "unique_containing_record_hits": len(containing_ids),
        "runtime_capture": "PENDING",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
