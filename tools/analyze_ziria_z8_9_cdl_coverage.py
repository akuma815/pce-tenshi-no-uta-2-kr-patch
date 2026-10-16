#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9b — PCEHawk CDL 세그먼트 기반 scene RAM coverage 분석기.

배경: whole-bus Lua 콜백 probe는 게임을 플레이 불가능한 속도로 만들었다.
PCEHawk의 Code Data Logger는 네이티브 속도로 "Super System Card RAM"
(물리 bank $68-$7F, 192 KiB) 접근을 바이트 단위로 기록한다.
CDL의 Data 플래그는 read와 write를 모두 포함하므로
cold = 플래그 0 = "CPU가 어떤 방식으로도 접근하지 않은 바이트"다.

세그먼트 프로토콜(필수 — 장면 재적재 오염 방지):
  BIOS의 mode-06 CD 로드는 CPU 복사이므로 로드 순간을 포함한 로그는
  scene RAM 전체가 접근된 것으로 오염된다. 따라서 각 세그먼트는
  "장면 로드 완료 후 New → 다음 장면 전환 전 Save"로 잘라야 한다.

  Seg A: 첫 필드 표시 → CDL New → 필드 콘텐츠 플레이(대사·NPC·Memo)
         → 전투 진입 **전에** Save (segment_a.cdl)
  Seg B: 전투 후 필드 복귀 → CDL New → 필드 콘텐츠 플레이
         → 다음 전환 전에 Save (segment_b.cdl)
  (탑 방문 후 복귀 등 세그먼트 추가 환영. Memo/초상화는 CD read가 없어
   세그먼트 내 포함 안전 — Z1 카탈로그 근거.)

사용:
  python -X utf8 tools/analyze_ziria_z8_9_cdl_coverage.py translation/cdl/*.cdl

검증(fail-closed):
- BIZHAWK-CDL-2 / PCE 헤더와 "Super System Card RAM" 블록(0x30000 B) 존재
- 세그먼트별 접근 비율 > CONTAMINATION_FRACTION 이면 장면 로드 포함으로
  판정하고 전체 분석을 중단
- 세그먼트 2개 미만이면 중단 (전투 후 복귀 세그먼트 필수)

분석: 전 세그먼트 OR → cold run → Z8.8 원문 회수 range와 병합 →
후보 region 표 + wire v2 feasibility 사전 점검.
결과는 후보일 뿐이며 canary 진단 빌드 게이트 전에는 승인되지 않는다.
"""

import io
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_COVERAGE = os.path.join(
    ROOT, "translation", "ziria_z8_9_field_init_coverage.tsv")
MIN_INIT_WINDOWS = 2
RECLAIM = os.path.join(
    ROOT, "module_relink", "z8_8_loader_allocation_abi", "source_reclaim_ranges.tsv")
OUT_DIR = os.path.join(ROOT, "module_relink", "z8_9_scene_ram_regions")
OUT_REGIONS = os.path.join(OUT_DIR, "candidate_regions.tsv")
OUT_MANIFEST = os.path.join(
    ROOT, "translation", "ziria_z8_9_scene_ram_region_candidates_manifest.json")

SCENE_BYTES = 0x30000
SCD_BLOCK = "Super System Card RAM"
BANK_FIRST = 0x68
MIN_REGION = 64
CONTAMINATION_FRACTION = 0.90
MIN_SEGMENTS = 2

NEED_INDEX = 2852
NEED_TEXT = 14640
NEED_GLYPH = 9360
NEED_TOTAL = NEED_INDEX + NEED_TEXT + NEED_GLYPH


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def read_7bit_string(f):
    length = 0
    shift = 0
    while True:
        b = f.read(1)
        if not b:
            fail("unexpected EOF in CDL string header")
        v = b[0]
        length |= (v & 0x7F) << shift
        if not v & 0x80:
            break
        shift += 7
    return f.read(length).decode("utf-8")


def parse_cdl(path):
    with open(path, "rb") as fh:
        f = io.BufferedReader(fh)
        magic = read_7bit_string(f)
        if magic == "BIZHAWK-CDL-2":
            subtype = read_7bit_string(f).rstrip(" ")
        elif magic == "BIZHAWK-CDL-1":
            subtype = "PCE"
        else:
            fail(f"{os.path.basename(path)}: not a BizHawk CDL file (magic {magic!r})")
        if subtype != "PCE":
            fail(f"{os.path.basename(path)}: CDL subtype {subtype!r}, expected PCE — PCEHawk 코어로 기록하세요")
        (count,) = struct.unpack("<i", f.read(4))
        blocks = {}
        for _ in range(count):
            key = read_7bit_string(f)
            (ln,) = struct.unpack("<i", f.read(4))
            blocks[key] = f.read(ln)
        return blocks


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
    paths = sorted(sys.argv[1:])
    if not paths:
        fail(
            "usage: analyze_ziria_z8_9_cdl_coverage.py <segment.cdl> [...]\n"
            "  PCEHawk Tools > Code Data Logger 세그먼트 캡처 파일들을 지정하세요.")
    union = bytearray(SCENE_BYTES)
    segments = []
    skipped = []
    for path in paths:
        if not os.path.isfile(path):
            fail(f"not found: {path}")
        blocks = parse_cdl(path)
        if SCD_BLOCK not in blocks:
            fail(
                f"{os.path.basename(path)}: '{SCD_BLOCK}' 블록 없음 — "
                "Super CD-ROM2 모드(PCEHawk + 3.0 카드)로 기록했는지 확인")
        data = blocks[SCD_BLOCK]
        if len(data) != SCENE_BYTES:
            fail(
                f"{os.path.basename(path)}: {SCD_BLOCK} 크기 {len(data):#x} != {SCENE_BYTES:#x}")
        touched = sum(1 for b in data if b)
        frac = touched / SCENE_BYTES
        if frac > CONTAMINATION_FRACTION:
            print(
                f"WARN: {os.path.basename(path)} 제외 — 접근 비율 {frac:.1%} > "
                f"{CONTAMINATION_FRACTION:.0%} (장면 로드 mode-06 CD read 포함 추정)")
            skipped.append({
                "file": os.path.basename(path),
                "touched_bytes": touched,
                "touched_fraction": round(frac, 4),
                "reason": "scene_load_contamination",
            })
            continue
        if touched == 0:
            print(f"WARN: {os.path.basename(path)} 제외 — 접근 0바이트(로깅 비활성 추정)")
            skipped.append({
                "file": os.path.basename(path),
                "touched_bytes": 0,
                "touched_fraction": 0.0,
                "reason": "empty_log",
            })
            continue
        segments.append({
            "file": os.path.basename(path),
            "touched_bytes": touched,
            "touched_fraction": round(frac, 4),
        })
        for i, b in enumerate(data):
            if b:
                union[i] = 1

    if len(segments) < MIN_SEGMENTS:
        fail(
            f"깨끗한 세그먼트 {len(segments)}개 < 최소 {MIN_SEGMENTS}개 "
            f"(제외 {len(skipped)}개) — 장면 전환(전투·탑·건물 출입·맵 이동)을 "
            "포함하지 않는 세그먼트를 추가 캡처하세요. 플레이 중 수시로 같은 "
            "파일에 Save를 덮어쓰면 전환 직전 상태가 보존됩니다.")

    # ---- 초기화 구간 coverage 차감 (canary FAIL 2026-07-27 재발 방지) ----
    # CDL 세그먼트는 장면 로드 직후 초기화 read(그래픽→VRAM 업로드 등)를
    # 포함하지 못한다. trace_ziria_z8_9_field_init_coverage.lua 캡처를
    # 필수 입력으로 받아 초기화 접근 바이트를 cold에서 제외한다.
    if not os.path.isfile(INIT_COVERAGE):
        fail(
            "초기화 coverage 없음: translation/ziria_z8_9_field_init_coverage.tsv\n"
            "  tools/trace_ziria_z8_9_field_init_coverage.lua로 LBA 482 로드 창을 "
            f"{MIN_INIT_WINDOWS}회 이상 캡처하세요 (canary 배경 깨짐의 원인이었던 "
            "init-only read를 제외하기 위한 필수 입력).")
    init_meta = {}
    init_touched_total = 0
    with open(INIT_COVERAGE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    it = iter(lines)
    for ln in it:
        parts = ln.split("\t")
        if parts[0] == "offset":
            break
        if len(parts) == 2:
            init_meta[parts[0]] = parts[1]
    if init_meta.get("format") != "ZIRIA-Z8-9-FIELD-INIT-COVERAGE-V1":
        fail("init coverage 형식 헤더 불일치")
    if int(init_meta.get("windows_done", "0")) < MIN_INIT_WINDOWS:
        fail(
            f"init coverage windows_done={init_meta.get('windows_done')} < "
            f"{MIN_INIT_WINDOWS} — 필드 재적재(건물 출입/전투 복귀)로 창을 추가 캡처하세요.")
    rows = 0
    for ln in it:
        off_hex, blob = ln.split("\t")
        off = int(off_hex, 16)
        if len(blob) != 256:
            fail(f"init coverage row {off_hex} 손상")
        for j, ch in enumerate(blob):
            if ch == "x":
                if not union[off + j]:
                    union[off + j] = 1
                init_touched_total += 1
            elif ch != ".":
                fail(f"init coverage 잘못된 심볼 {ch!r}")
        rows += 1
    if rows != SCENE_BYTES // 256:
        fail(f"init coverage rows {rows} != {SCENE_BYTES // 256}")

    # cold runs
    cold = []
    start = None
    for i in range(SCENE_BYTES + 1):
        is_cold = i < SCENE_BYTES and union[i] == 0
        if is_cold and start is None:
            start = i
        elif not is_cold and start is not None:
            if i - start >= MIN_REGION:
                cold.append((start, i))
            start = None
    cold_total = SCENE_BYTES - sum(1 for b in union if b)

    reclaim = parse_reclaim()
    for s, e in reclaim:
        if not (0 <= s < e <= SCENE_BYTES):
            fail(f"reclaim range out of bounds {s:#x}..{e:#x}")

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
        "version": 2,
        "capture_method": "PCEHawk CDL segments (native-speed, read+write via Data/Code/Stack/BlockXFer flags)"
                          " + field init window bus coverage",
        "segments": segments,
        "skipped_segments": skipped,
        "init_coverage": {
            "windows_done": int(init_meta.get("windows_done", "0")),
            "access_events": int(init_meta.get("access_events", "0")),
            "touched_bytes": init_touched_total,
        },
        "rules": {
            "cold_definition": "CDL flags 0 in every segment (no CPU access of any kind)",
            "min_region": MIN_REGION,
            "contamination_fraction": CONTAMINATION_FRACTION,
            "min_segments": MIN_SEGMENTS,
        },
        "cold_total_bytes": cold_total,
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

    print(f"Z8.9b CDL COVERAGE: {manifest['status']}")
    for s in segments:
        print(f"  segment {s['file']}: touched {s['touched_bytes']}/{SCENE_BYTES} ({s['touched_fraction']:.1%})")
    print(f"  cold total: {cold_total} B, cold runs>={MIN_REGION}B: {len(cold)}")
    print(f"  candidate regions: {len(regions)}, total {total} B, largest {largest} B")
    print(f"  need: index {NEED_INDEX}(연속) + text {NEED_TEXT} + glyph {NEED_GLYPH} = {NEED_TOTAL} B")


if __name__ == "__main__":
    main()
