#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9a — Track02 디스크 참조 전수 감사.

원본을 수정하지 않는 읽기 전용 감사기다.

1. 원본 BIN의 Track02(MODE1/2048) 슬라이스 해시를 고정 기준과 대조한다.
2. primary/scene 두 55-entry 디렉터리와 시스템/엔진 예약 구간의 정적 참조
   합집합을 계산한다.
3. translation/*.tsv 런타임 trace 전부에서 관측된 CD_READ (lba, count)를
   수집해 런타임 참조 합집합을 만든다.
4. `JSR $E009` 콜사이트를 Track02 전역에서 열거해 테이블 비경유 read의
   존재 증거로 기록한다(승인 판단에는 사용하지 않고 위험 목록으로만 남긴다).
5. 순수 fill 섹터 run을 스캔한다.
6. 승인 규칙(전부 충족해야 승인):
   - 정적 참조 합집합과 겹치지 않는다.
   - 런타임 관측 read extent와 겹치지 않는다.
   - run 전체가 단일 fill 값 0x00이고 길이가 MIN_APPROVE_RUN 이상이다.
   - LBA >= FIRST_SCENE_SLOT (시스템/부트 영역 전체 보수 예약).

산출물:
  translation/ziria_z8_9_disc_reference_audit_manifest.json
  module_relink/z8_9_disc_audit/referenced_extents.tsv
  module_relink/z8_9_disc_audit/approved_sectors.tsv

결정성: 타임스탬프를 기록하지 않으며 동일 입력에서 동일 바이트를 생성한다.
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BIN_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
TRACK02_BIN_OFFSET = 7914480          # CUE: TRACK 02 MODE1/2048
TRACK02_SECTORS = 9328
TRACK02_SHA256 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"

PRIMARY_TABLE_OFFSET = 0x424A5        # Z1: physical-grid 디렉터리
SCENE_TABLE_OFFSET = 0x83531          # Z1: field.main_engine 장면 디렉터리
TABLE_ENTRIES = 55

FIRST_SCENE_SLOT = 290                # 이보다 앞은 시스템/부트/엔진 보수 예약
MIN_APPROVE_RUN = 8                   # 섹터
APPROVE_FILL_VALUE = 0x00

# Z1/Z2에서 확정된 비-테이블 정적 모듈 extent (lba, sectors, name)
KNOWN_MODULES = [
    (0, FIRST_SCENE_SLOT, "system_boot_engine_reserved_block"),
]

TRACE_DIR = os.path.join(ROOT, "translation")
OUT_MANIFEST = os.path.join(TRACE_DIR, "ziria_z8_9_disc_reference_audit_manifest.json")
OUT_DIR = os.path.join(ROOT, "module_relink", "z8_9_disc_audit")
OUT_REFERENCED = os.path.join(OUT_DIR, "referenced_extents.tsv")
OUT_APPROVED = os.path.join(OUT_DIR, "approved_sectors.tsv")


def sha256_stream(path, offset=0, length=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(offset)
        remaining = length if length is not None else os.path.getsize(path) - offset
        while remaining:
            chunk = f.read(min(1 << 22, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest().upper()


def load_track02():
    if not os.path.isfile(BIN_PATH):
        sys.exit("FAIL: original BIN not found")
    got = sha256_stream(BIN_PATH, TRACK02_BIN_OFFSET, TRACK02_SECTORS * 2048)
    if got != TRACK02_SHA256:
        sys.exit(f"FAIL: track02 slice hash mismatch {got}")
    with open(BIN_PATH, "rb") as f:
        f.seek(TRACK02_BIN_OFFSET)
        return f.read(TRACK02_SECTORS * 2048)


def parse_table(data, offset):
    entries = []
    raw = data[offset:offset + TABLE_ENTRIES * 4]
    for i in range(TABLE_ENTRIES):
        hi, mid, lo, cnt = raw[i * 4:i * 4 + 4]
        lba = (hi << 16) | (mid << 8) | lo
        entries.append({"entry": i, "lba": lba, "sector_count": cnt})
    return entries


def harvest_runtime_extents():
    """translation/*.tsv 전체에서 (lba, count) 관측치를 보수적으로 수집한다.

    과잉 수집은 승인 공간을 줄일 뿐이므로 안전 방향이다.
    """
    extents = {}
    files = sorted(f for f in os.listdir(TRACE_DIR) if f.endswith(".tsv"))
    for name in files:
        path = os.path.join(TRACE_DIR, name)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        if not lines:
            continue
        header = lines[0].split("\t")
        cols = {c.strip().lower(): i for i, c in enumerate(header)}
        pairs = []
        # key-value 프리앰블 형식 (task7 lifetime trace)
        kv = {}
        for ln in lines[:12]:
            parts = ln.split("\t")
            if len(parts) == 2:
                kv[parts[0].strip().lower()] = parts[1].strip()
        if "target_lba" in kv and "target_count" in kv:
            try:
                pairs.append((int(kv["target_lba"]), int(kv["target_count"])))
            except ValueError:
                pass
        # 컬럼 형식
        for lc, cc in (("lba", "count"), ("active_lba", "active_count")):
            if lc in cols and cc in cols:
                li, ci = cols[lc], cols[cc]
                for ln in lines[1:]:
                    parts = ln.split("\t")
                    if len(parts) <= max(li, ci):
                        continue
                    try:
                        lba = int(parts[li])
                        cnt = int(parts[ci])
                    except ValueError:
                        continue
                    if lba <= 0 or cnt <= 0 or cnt > 512:
                        continue
                    pairs.append((lba, cnt))
        for lba, cnt in pairs:
            key = (lba, cnt)
            if key not in extents:
                extents[key] = set()
            extents[key].add(name)
    return [
        {"lba": lba, "sector_count": cnt, "sources": sorted(srcs)}
        for (lba, cnt), srcs in sorted(extents.items())
    ]


def scan_e009_callsites(data):
    sites = []
    idx = data.find(b"\x20\x09\xe0")
    while idx != -1:
        sites.append(idx)
        idx = data.find(b"\x20\x09\xe0", idx + 1)
    return sites


def scan_fill_runs(data):
    runs = []
    cur_start, cur_val = None, None
    for lba in range(TRACK02_SECTORS):
        sec = data[lba * 2048:(lba + 1) * 2048]
        val = sec[0]
        is_fill = sec.count(val) == 2048
        if is_fill and cur_val == val and cur_start is not None:
            continue
        if cur_start is not None:
            runs.append((cur_start, lba, cur_val))
        if is_fill:
            cur_start, cur_val = lba, val
        else:
            cur_start, cur_val = None, None
    if cur_start is not None:
        runs.append((cur_start, TRACK02_SECTORS, cur_val))
    return [(s, e, v) for s, e, v in runs if e - s >= 2]


def merge_extents(extents):
    ivs = sorted((s, e) for s, e in extents)
    merged = []
    for s, e in ivs:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def main():
    data = load_track02()

    primary = parse_table(data, PRIMARY_TABLE_OFFSET)
    scene = parse_table(data, SCENE_TABLE_OFFSET)
    runtime = harvest_runtime_extents()
    e009 = scan_e009_callsites(data)
    fills = scan_fill_runs(data)

    static_extents = [(m[0], m[0] + m[1]) for m in KNOWN_MODULES]
    static_extents += [(e["lba"], e["lba"] + e["sector_count"]) for e in primary]
    static_extents += [(e["lba"], e["lba"] + e["sector_count"]) for e in scene]
    runtime_extents = [(e["lba"], e["lba"] + e["sector_count"]) for e in runtime]

    referenced = merge_extents(static_extents + runtime_extents)

    gaps = []
    prev = 0
    for s, e in referenced:
        if s > prev:
            gaps.append((prev, s))
        prev = max(prev, e)
    if prev < TRACK02_SECTORS:
        gaps.append((prev, TRACK02_SECTORS))

    approved = []
    rejected = []
    for gs, ge in gaps:
        covered = []
        for fs, fe, fv in fills:
            s, e = max(gs, fs), min(ge, fe)
            if e - s <= 0:
                continue
            entry = {"lba_start": s, "lba_end": e, "sectors": e - s, "fill_value": fv}
            if fv == APPROVE_FILL_VALUE and e - s >= MIN_APPROVE_RUN and s >= FIRST_SCENE_SLOT:
                approved.append(entry)
            else:
                rejected.append({**entry, "reason": "fill_rule_not_met"})
            covered.append((s, e))
        # gap 내 비-fill 잔여는 전부 거부
        cur = gs
        for s, e in sorted(covered):
            if s > cur:
                rejected.append({
                    "lba_start": cur, "lba_end": s, "sectors": s - cur,
                    "fill_value": None,
                    "reason": "unreferenced_but_nonfill_presumed_externally_referenced",
                })
            cur = max(cur, e)
        if cur < ge:
            rejected.append({
                "lba_start": cur, "lba_end": ge, "sectors": ge - cur,
                "fill_value": None,
                "reason": "unreferenced_but_nonfill_presumed_externally_referenced",
            })

    # 승인 구간 무결성 재검: 내용이 실제로 전부 0x00인지 바이트 단위 재확인
    for a in approved:
        blob = data[a["lba_start"] * 2048:a["lba_end"] * 2048]
        if blob.count(APPROVE_FILL_VALUE) != len(blob):
            sys.exit(f"FAIL: approved region {a} is not pure fill on re-read")

    manifest = {
        "format": "ZIRIA-Z8-9-DISC-REFERENCE-AUDIT",
        "version": 1,
        "source": {
            "bin": os.path.basename(BIN_PATH),
            "bin_sha256": BIN_SHA256,
            "track02_bin_offset": TRACK02_BIN_OFFSET,
            "track02_sectors": TRACK02_SECTORS,
            "track02_sha256": TRACK02_SHA256,
            "track_mode": "MODE1/2048",
        },
        "rules": {
            "min_approve_run_sectors": MIN_APPROVE_RUN,
            "approve_fill_value": APPROVE_FILL_VALUE,
            "first_scene_slot_reserved_below": FIRST_SCENE_SLOT,
            "nonfill_unreferenced_policy": "reject_as_presumed_externally_referenced",
        },
        "static_references": {
            "known_modules": [
                {"lba": m[0], "sector_count": m[1], "name": m[2]} for m in KNOWN_MODULES
            ],
            "primary_table_offset": hex(PRIMARY_TABLE_OFFSET),
            "primary_table": primary,
            "scene_table_offset": hex(SCENE_TABLE_OFFSET),
            "scene_table": scene,
        },
        "runtime_observed_extents": runtime,
        "e009_callsite_track02_offsets": [hex(x) for x in e009],
        "e009_callsite_count": len(e009),
        "fill_runs": [
            {"lba_start": s, "lba_end": e, "sectors": e - s, "fill_value": v}
            for s, e, v in fills
        ],
        "referenced_merged": [
            {"lba_start": s, "lba_end": e, "sectors": e - s} for s, e in referenced
        ],
        "approved_regions": approved,
        "rejected_regions": sorted(rejected, key=lambda r: r["lba_start"]),
        "approved_total_sectors": sum(a["sectors"] for a in approved),
        "approved_total_bytes": sum(a["sectors"] for a in approved) * 2048,
        "status": "AUDIT_PASS" if approved else "AUDIT_PASS_NO_APPROVED_REGION",
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(OUT_REFERENCED, "w", encoding="utf-8", newline="\n") as f:
        f.write("lba_start\tlba_end\tsectors\n")
        for s, e in referenced:
            f.write(f"{s}\t{e}\t{e - s}\n")
    with open(OUT_APPROVED, "w", encoding="utf-8", newline="\n") as f:
        f.write("lba_start\tlba_end\tsectors\tbytes\tfill_value\n")
        for a in approved:
            f.write(
                f"{a['lba_start']}\t{a['lba_end']}\t{a['sectors']}\t"
                f"{a['sectors'] * 2048}\t{a['fill_value']:02X}\n"
            )

    print(f"Z8.9a DISC AUDIT: {manifest['status']}")
    print(f"  referenced merged extents : {len(referenced)}")
    print(f"  runtime observed extents  : {len(runtime)}")
    print(f"  e009 callsites (info)     : {len(e009)}")
    for a in approved:
        print(
            f"  APPROVED LBA {a['lba_start']}..{a['lba_end']} "
            f"({a['sectors']} sectors, {a['sectors'] * 2048} bytes, fill {a['fill_value']:02X})"
        )
    print(f"  approved total            : {manifest['approved_total_bytes']} bytes")


if __name__ == "__main__":
    main()
