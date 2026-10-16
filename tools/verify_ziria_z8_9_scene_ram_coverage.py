#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ DEPRECATED (2026-07-27): Lua whole-bus probe가 속도 문제로 폐기되어
이 검증기도 사용하지 않는다. 대체: tools/analyze_ziria_z8_9_cdl_coverage.py
(PCEHawk Code Data Logger 세그먼트 캡처 기반).

Z8.9b coverage 캡처 오프라인 검증·후보 region 분석기.

trace_ziria_z8_9_scene_ram_coverage.lua가 기록한 캡처를 검증하고,
Z8.8 원문 회수 range와 병합해 wire v2 배치용 후보 region 표를 만든다.

검증:
1. coverage 파일 형식·행 수·심볼 무결성.
2. cold run 파일이 coverage에서 재계산한 결과와 일치.
3. 캡처 최소 요건: field_generations >= 2 (전투/탑 후 복귀 재적재 포함),
   read/write 이벤트 > 0, CD_READ 관측 > 0.

분석:
- cold region  = read 0 AND write 0 인 연속 구간 (>= MIN_COLD)
- reclaim region = Z8.8 원문 회수 range (redirect 후 해제되는 원문 자리)
- 두 집합의 합집합에서 겹침을 병합한 후보 region 표를 만들고
  Z8.7 자산(index 2,852 / text 14,640 / glyph 9,360 B) 대비
  총량과 index 연속성 요구를 사전 점검한다.

주의: 이 결과는 후보일 뿐이다. canary 진단 빌드 게이트를 통과하기 전에는
어느 region도 승인되지 않는다.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVERAGE = os.path.join(ROOT, "translation", "ziria_z8_9_scene_ram_coverage.tsv")
COLD_RUNS = os.path.join(ROOT, "translation", "ziria_z8_9_scene_ram_cold_runs.tsv")
RECLAIM = os.path.join(
    ROOT, "module_relink", "z8_8_loader_allocation_abi", "source_reclaim_ranges.tsv")
OUT_DIR = os.path.join(ROOT, "module_relink", "z8_9_scene_ram_regions")
OUT_REGIONS = os.path.join(OUT_DIR, "candidate_regions.tsv")
OUT_MANIFEST = os.path.join(
    ROOT, "translation", "ziria_z8_9_scene_ram_region_candidates_manifest.json")

SCENE_BYTES = 0x30000
MIN_COLD = 32          # probe MIN_RUN과 일치해야 한다
MIN_REGION = 64        # 후보 region 최소 크기(작은 조각은 할당기 비용만 늘린다)
BANK_FIRST = 0x68

# Z8.7 wire 자산 요구 (translation/ziria_z8_field_redirect_format_manifest.json)
NEED_INDEX = 2852
NEED_TEXT = 14640
NEED_GLYPH = 9360
NEED_TOTAL = NEED_INDEX + NEED_TEXT + NEED_GLYPH

MIN_GENERATIONS = 2


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def parse_coverage():
    if not os.path.isfile(COVERAGE):
        fail(
            "coverage capture not found: translation/ziria_z8_9_scene_ram_coverage.tsv\n"
            "  BizHawk(PCEHawk)에서 tools/trace_ziria_z8_9_scene_ram_coverage.lua로 "
            "회귀 경로를 주행한 뒤 다시 실행하세요.")
    meta = {}
    flags = bytearray(SCENE_BYTES)
    rows = 0
    with open(COVERAGE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    it = iter(lines)
    for ln in it:
        parts = ln.split("\t")
        if parts[0] == "offset":
            break
        if len(parts) == 2:
            meta[parts[0]] = parts[1]
    if meta.get("format") != "ZIRIA-Z8-9-SCENE-RAM-COVERAGE-V1":
        fail("unexpected coverage format header")
    sym = {".": 0, "r": 1, "w": 2, "b": 3}
    for ln in it:
        off_hex, blob = ln.split("\t")
        off = int(off_hex, 16)
        if len(blob) != 256:
            fail(f"coverage row at {off_hex} has {len(blob)} symbols")
        for j, ch in enumerate(blob):
            if ch not in sym:
                fail(f"invalid symbol {ch!r} at {off_hex}+{j}")
            flags[off + j] = sym[ch]
        rows += 1
    if rows != SCENE_BYTES // 256:
        fail(f"coverage rows {rows} != {SCENE_BYTES // 256}")
    return meta, flags


def cold_runs_from(flags, min_len):
    runs = []
    start = None
    for i in range(SCENE_BYTES + 1):
        cold = i < SCENE_BYTES and flags[i] == 0
        if cold and start is None:
            start = i
        elif not cold and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    return runs


def parse_probe_cold_runs():
    runs = []
    with open(COLD_RUNS, "r", encoding="utf-8") as f:
        header = f.readline()
        if not header.startswith("offset_start"):
            fail("cold runs header mismatch")
        for ln in f.read().splitlines():
            s, e, ln_len, _bank, _boff = ln.split("\t")
            runs.append((int(s, 16), int(e, 16)))
    return runs


def parse_reclaim():
    ranges = []
    with open(RECLAIM, "r", encoding="utf-8") as f:
        f.readline()
        for ln in f.read().splitlines():
            s, e, _b = ln.split("\t")
            ranges.append((int(s, 16), int(e, 16)))
    return ranges


def merge(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def main():
    meta, flags = parse_coverage()

    gens = int(meta.get("field_generations", "0"))
    reads = int(meta.get("read_events", "0"))
    writes = int(meta.get("write_events", "0"))
    cds = int(meta.get("cd_records", "0"))
    identity = meta.get("scene_identity_source", "")
    if reads == 0 or writes == 0:
        fail("capture has zero read/write events — PCEHawk 코어인지 확인하세요")
    if cds == 0 or identity != "observed_mode06_cd_read":
        fail("capture never observed a mode-06 CD read — 전투/탑 전환을 포함해 주행하세요")
    if gens < MIN_GENERATIONS:
        fail(f"field_generations={gens} < {MIN_GENERATIONS} — 전투/탑 후 필드 복귀까지 주행하세요")

    recomputed = cold_runs_from(flags, MIN_COLD)
    reported = parse_probe_cold_runs()
    if recomputed != reported:
        fail(
            f"cold runs mismatch: probe reported {len(reported)}, "
            f"recomputed {len(recomputed)} — flush 중 캡처가 잘렸을 수 있습니다")

    cold = [(s, e) for s, e in recomputed if e - s >= MIN_REGION]
    reclaim = parse_reclaim()
    for s, e in reclaim:
        if not (0 <= s < e <= SCENE_BYTES):
            fail(f"reclaim range out of scene bounds {s:#x}..{e:#x}")

    tagged = [(s, e, "cold") for s, e in cold] + [(s, e, "reclaim") for s, e in reclaim]
    merged = merge([(s, e) for s, e, _t in tagged])

    def sources_for(s, e):
        srcs = set()
        for rs, re_, t in tagged:
            if max(s, rs) < min(e, re_):
                srcs.add(t)
        return "+".join(sorted(srcs))

    regions = [
        {
            "offset_start": s,
            "offset_end": e,
            "bytes": e - s,
            "bank": BANK_FIRST + s // 0x2000,
            "crosses_bank": (s // 0x2000) != ((e - 1) // 0x2000),
            "source": sources_for(s, e),
        }
        for s, e in merged
        if e - s >= MIN_REGION
    ]

    total = sum(r["bytes"] for r in regions)
    largest = max((r["bytes"] for r in regions), default=0)
    feasibility = {
        "need_index_contiguous": NEED_INDEX,
        "need_text": NEED_TEXT,
        "need_glyph": NEED_GLYPH,
        "need_total": NEED_TOTAL,
        "candidate_total": total,
        "candidate_largest": largest,
        "total_sufficient": total >= NEED_TOTAL,
        "index_placeable": largest >= NEED_INDEX,
    }

    manifest = {
        "format": "ZIRIA-Z8-9-SCENE-RAM-REGION-CANDIDATES",
        "version": 1,
        "capture_meta": meta,
        "rules": {
            "min_cold_run": MIN_COLD,
            "min_region": MIN_REGION,
            "cold_definition": "no CPU read AND no CPU write while field scene active",
            "min_field_generations": MIN_GENERATIONS,
        },
        "cold_runs": [
            {"offset_start": s, "offset_end": e, "bytes": e - s} for s, e in cold
        ],
        "reclaim_ranges_count": len(reclaim),
        "candidate_regions": regions,
        "feasibility_precheck": feasibility,
        "status": (
            "CANDIDATES_FEASIBLE_PENDING_CANARY"
            if feasibility["total_sufficient"] and feasibility["index_placeable"]
            else "CANDIDATES_INSUFFICIENT_ESCALATE_A2_OR_COMPRESSION"
        ),
        "approval": "NONE — canary 진단 빌드 게이트 통과 전에는 어느 region도 승인되지 않는다",
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(OUT_REGIONS, "w", encoding="utf-8", newline="\n") as f:
        f.write("offset_start\toffset_end\tbytes\tbank\tcrosses_bank\tsource\n")
        for r in regions:
            f.write(
                f"{r['offset_start']:06X}\t{r['offset_end']:06X}\t{r['bytes']}\t"
                f"{r['bank']:02X}\t{int(r['crosses_bank'])}\t{r['source']}\n")

    print(f"Z8.9b SCENE RAM COVERAGE VERIFY: {manifest['status']}")
    print(f"  field_generations={gens} reads={reads} writes={writes} cd={cds}")
    print(f"  cold runs>={MIN_REGION}B: {len(cold)}")
    print(f"  candidate regions: {len(regions)}, total {total} B, largest {largest} B")
    print(f"  need: index {NEED_INDEX}(연속) + text {NEED_TEXT} + glyph {NEED_GLYPH} = {NEED_TOTAL} B")


if __name__ == "__main__":
    main()
