#!/usr/bin/env python3
"""Summarize and gate the Z8.3 BizHawk field source-key runtime capture."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "translation" / "ziria_z8_field_source_key_runtime_trace.tsv"
STATUS = ROOT / "translation" / "ziria_z8_field_source_key_runtime_status.txt"
LOOKUP = ROOT / "translation" / "ziria_z8_field_source_key_lookup.tsv"
PROBE_MANIFEST = ROOT / "translation" / "ziria_z8_field_source_key_probe_manifest.json"
OUTPUT = ROOT / "translation" / "ziria_z8_field_source_key_runtime_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_4_field_source_key_runtime_result.md"
FIELD_LBA = 482
FIELD_COUNT = 96
FIELD_MODE = 0x06
BANK_BASE = 0x68


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def read_status(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, value = line.split("=", 1)
        result[key] = value
    return result


def main() -> None:
    for path in (TRACE, STATUS, LOOKUP, PROBE_MANIFEST):
        if not path.is_file():
            raise FileNotFoundError(path)

    trace = read_tsv(TRACE)
    lookup_rows = read_tsv(LOOKUP)
    lookup = {row["source_key"]: row for row in lookup_rows}
    probe_manifest = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))
    status = read_status(STATUS)
    if len(lookup) != 236:
        raise ValueError(f"lookup denominator: {len(lookup)}")
    if status.get("status") not in {"running", "closed"}:
        raise ValueError(f"runtime status: {status.get('status')}")

    events = Counter(row["event"] for row in trace)
    field_stream = [
        row
        for row in trace
        if row["event"] in {"START_HIT", "STREAM_NONSTART"}
        and int(row["active_lba"]) == FIELD_LBA
        and int(row["active_count"]) == FIELD_COUNT
        and int(row["active_mode"], 16) == FIELD_MODE
    ]
    hits = [row for row in field_stream if row["event"] == "START_HIT"]
    unique_hit_ids = sorted({row["catalog_id"] for row in hits})
    expected_hit_ids = sorted(probe_manifest["offline_replay"]["exact_start_ids"])

    formula_mismatches: list[int] = []
    lookup_mismatches: list[int] = []
    identity_mismatches: list[int] = []
    for index, row in enumerate(hits, start=1):
        logical = int(row["logical"], 16)
        mpr = int(row["mpr"], 16)
        expected_key = (mpr - BANK_BASE) * 0x2000 + (logical & 0x1FFF)
        if row["source_key"] != f"{expected_key:06X}":
            formula_mismatches.append(index)
        item = lookup.get(row["source_key"])
        if (
            item is None
            or item["id"] != row["catalog_id"]
            or item["source_iso_offset"] != row["catalog_iso_offset"]
        ):
            lookup_mismatches.append(index)
        if row["scene_identity_source"] != "observed_mode06_cd_read":
            identity_mismatches.append(index)

    cd_reads = [row for row in trace if row["event"] == "CD_READ"]
    cd_transitions: list[dict[str, int | str]] = []
    for row in cd_reads:
        item = {
            "frame": int(row["frame"]),
            "lba": int(row["active_lba"]),
            "count": int(row["active_count"]),
            "mode": row["active_mode"],
            "scene_identity_source": row["scene_identity_source"],
        }
        if not cd_transitions or item["lba"] != cd_transitions[-1]["lba"]:
            cd_transitions.append(item)

    pass_gate = (
        len(trace) > 0
        and len(field_stream) > 0
        and len(hits) == 9
        and unique_hit_ids == expected_hit_ids
        and not formula_mismatches
        and not lookup_mismatches
        and not identity_mismatches
        and any(item["lba"] == FIELD_LBA for item in cd_transitions)
        and any(item["lba"] != FIELD_LBA for item in cd_transitions)
    )
    if not pass_gate:
        raise ValueError("runtime gate failed")

    manifest = {
        "format": "ZIRIA-Z8-FIELD-SOURCE-KEY-RUNTIME",
        "version": 1,
        "task": "Z8-v4-field-source-key-runtime-gate",
        "status": "RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN",
        "mutation_scope": "analysis outputs only; no CUE/BIN/ISO mutation",
        "inputs": {
            "probe_manifest": {
                "path": str(PROBE_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(PROBE_MANIFEST),
            },
            "runtime_trace": {
                "path": str(TRACE.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(TRACE),
            },
            "lookup": {
                "path": str(LOOKUP.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(LOOKUP),
            },
        },
        "runtime_status_snapshot": status,
        "trace": {
            "rows": len(trace),
            "event_counts": dict(sorted(events.items())),
            "field_scene_stream_rows": len(field_stream),
            "start_hits": len(hits),
            "unique_start_hit_ids": unique_hit_ids,
            "unique_start_hit_count": len(unique_hit_ids),
            "source_key_formula_mismatches": len(formula_mismatches),
            "lookup_mismatches": len(lookup_mismatches),
            "scene_identity_mismatches": len(identity_mismatches),
            "cd_transitions": cd_transitions,
        },
        "runtime_gate": {
            "status": "PASS",
            "user_route_observation": (
                "first dialogue -> Memo enter/return -> first battle/field return "
                "-> tower entry completed"
            ),
            "proved": [
                "all eight offline exact-start IDs were observed in a fresh runtime capture",
                "all START_HIT rows round-trip through the canonical MPR source-key formula",
                "all START_HIT rows match the 236-row lookup ID and ISO offset",
                "field-scene identity was refreshed by an observed mode-06 CD read",
                "later mode-06 loads changed scene identity without emulator failure",
            ],
            "not_proved": [
                "complete runtime consumption coverage for all 236 catalogue records",
                "static event-bytecode reference denominator for the remaining 228 records",
                "redirect/index storage format or hook ABI",
            ],
        },
        "redirect_index": {
            "status": "NOT_BUILT",
            "reason": "text reference denominator remains open",
        },
        "outputs": {
            "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        },
    }
    OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    transitions = ", ".join(
        f"LBA {item['lba']}@frame {item['frame']}" for item in cd_transitions
    )
    REPORT.write_text(
        "\n".join(
            [
                "# Z8.4 field source-key runtime result",
                "",
                "## 판정",
                "",
                "- 상태: **RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN**",
                f"- 런타임 trace: **{len(trace)}행**",
                f"- field scene stream: **{len(field_stream)}회**",
                f"- START_HIT: **{len(hits)}회 / 고유 {len(unique_hit_ids)}개**",
                "- source-key 수식 불일치: **0건**",
                "- lookup ID/ISO 위치 불일치: **0건**",
                "- scene identity 불일치: **0건**",
                f"- mode-06 전환: {transitions}",
                "",
                "오프라인 재생에서 확인한 정확한 시작 ID 8개가 새 BizHawk 런타임에서도",
                "모두 관측됐다. source key 계산과 236행 lookup 왕복은 PASS다.",
                "",
                "## 남은 차단 조건",
                "",
                "이번 경로는 source-key 산식과 관측된 소비자를 검증했지만 236개 전체의",
                "참조 분모를 닫지는 못했다. 미관측 228개에 대한 정적 event-bytecode",
                "decoder 또는 동등한 전체 coverage가 확보되기 전에는 redirect/index를",
                "생성하지 않는다.",
                "",
                "이번 분석은 CUE/BIN/ISO를 수정하지 않았다.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(manifest["trace"], ensure_ascii=False, indent=2))
    print(f"manifest_sha256={sha256(OUTPUT)}")


if __name__ == "__main__":
    main()
