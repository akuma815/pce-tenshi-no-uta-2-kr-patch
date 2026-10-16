#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9c — wire v2 배치 시뮬레이션 (디스크 무수정).

Z8.9b에서 확보한 후보 region(cold + 원문 회수)에 Z8.7 자산을 실제로
배치해 보고, 성공하면 scene-절대 offset 기반 wire v2 산출물을 만든다.

배치 규칙:
1. 후보 region을 8 KiB bank 경계에서 분할한 "window"(bank 내 연속 구간)를
   할당 단위로 한다. Z8.7의 bank-crossing 금지 규약을 모든 자산에 적용한다.
2. index(32B header + 235*12B)는 단일 window에 연속 배치한다.
3. glyph는 18B 레코드 단위로 window들에 채우고, 520개 glyph의 scene-절대
   offset을 담는 glyph offset table(520*3B, 단일 window 연속)을 둔다.
4. 번역 text는 (target_offset, length) 고유 blob 단위로 중복 제거를 유지한
   채 first-fit-decreasing으로 배치한다. blob은 window를 넘지 않는다.
5. 배치 결과가 후보 region 안에 있고 서로 겹치지 않음을 전수 검증한다.

canary 계획:
- canary로 채울 수 있는 바이트 = 배치에 사용된 바이트 ∩ cold ∖ reclaim.
  (reclaim 바이트는 redirect 전에는 살아 있는 원문이므로 canary 금지.)
- canary 불가능한 배치 바이트(reclaim 유래)는 canary 게이트에서 검증되지
  않음을 manifest에 명시한다.

이 단계는 CUE/BIN/ISO를 수정하지 않는다. 산출물은 시뮬레이션 결과다.
"""

import csv
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Z87_DIR = os.path.join(ROOT, "module_relink", "z8_field_redirect_format")
REGIONS_TSV = os.path.join(ROOT, "module_relink", "z8_9_scene_ram_regions", "candidate_regions.tsv")
COVERAGE_MANIFEST = os.path.join(
    ROOT, "translation", "ziria_z8_9_scene_ram_region_candidates_manifest.json")
RECLAIM = os.path.join(
    ROOT, "module_relink", "z8_8_loader_allocation_abi", "source_reclaim_ranges.tsv")

OUT_DIR = os.path.join(ROOT, "module_relink", "z8_9_wire_v2")
OUT_MANIFEST = os.path.join(ROOT, "translation", "ziria_z8_9_wire_v2_placement_manifest.json")

SCENE_BYTES = 0x30000
BANK = 0x2000
BANK_FIRST = 0x68
GLYPH_SIZE = 18
INDEX_HEADER = 32
RECORD_SIZE = 12


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def load_records():
    path = os.path.join(Z87_DIR, "field_dialogue_records.tsv")
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for r in rd:
            rows.append({
                "ordinal": int(r["ordinal"]),
                "id": r["id"],
                "source_key": int(r["source_key"], 16),
                "target_offset": int(r["target_offset"], 16),
                "original_length": int(r["original_length"]),
                "translated_length": int(r["translated_length"]),
                "kind_code": int(r["kind_code"], 16),
                "flags": int(r["flags"], 16),
            })
    if len(rows) != 235:
        fail(f"records {len(rows)} != 235")
    return rows


def load_windows():
    if not os.path.isfile(REGIONS_TSV):
        fail("candidate_regions.tsv 없음 — analyze_ziria_z8_9_cdl_coverage.py를 먼저 실행")
    regions = []
    with open(REGIONS_TSV, "r", encoding="utf-8") as f:
        f.readline()
        for ln in f.read().splitlines():
            s, e, _b, _bank, _cross, src = ln.split("\t")
            regions.append((int(s, 16), int(e, 16), src))
    windows = []
    for s, e, src in regions:
        cur = s
        while cur < e:
            bank_end = (cur // BANK + 1) * BANK
            w_end = min(e, bank_end)
            windows.append([cur, w_end, src])
            cur = w_end
    return regions, windows


def load_byte_classes():
    cov = json.load(open(COVERAGE_MANIFEST, encoding="utf-8"))
    cold = bytearray(SCENE_BYTES)
    for r in cov["cold_runs"]:
        for i in range(r["offset_start"], r["offset_end"]):
            cold[i] = 1
    reclaim = bytearray(SCENE_BYTES)
    with open(RECLAIM, "r", encoding="utf-8") as f:
        f.readline()
        for ln in f.read().splitlines():
            s, e, _b = ln.split("\t")
            for i in range(int(s, 16), int(e, 16)):
                reclaim[i] = 1
    return cold, reclaim, cov


def main():
    records = load_records()
    text_blob = open(os.path.join(Z87_DIR, "field_dialogue_text.bin"), "rb").read()
    glyphs = open(os.path.join(Z87_DIR, "field_dialogue_glyphs_packed18.bin"), "rb").read()
    if len(glyphs) % GLYPH_SIZE:
        fail("glyph pool size not multiple of 18")
    glyph_count = len(glyphs) // GLYPH_SIZE

    regions, windows = load_windows()
    cold, reclaim, cov = load_byte_classes()

    # ---- 할당기 ----
    # windows: [start, end, src]; free 공간은 앞에서부터 소비한다.
    windows.sort(key=lambda w: -(w[1] - w[0]))
    placements = []  # (asset, name, start, end)

    def alloc(size, label):
        for w in windows:
            if w[1] - w[0] >= size:
                start = w[0]
                w[0] += size
                placements.append((label[0], label[1], start, start + size))
                return start
        return None

    # 1. index (연속, 단일 window)
    index_size = INDEX_HEADER + RECORD_SIZE * len(records)
    index_at = alloc(index_size, ("index", "index"))
    if index_at is None:
        fail(f"index {index_size}B를 담을 window 없음")

    # 2. glyph offset table (연속, 단일 window)
    gtab_size = glyph_count * 3
    gtab_at = alloc(gtab_size, ("glyph_table", "glyph_table"))
    if gtab_at is None:
        fail(f"glyph table {gtab_size}B를 담을 window 없음")

    # 3. glyphs: 18B 단위로 큰 window부터 채움
    glyph_offsets = []
    gi = 0
    while gi < glyph_count:
        placed = False
        for w in windows:
            cap = (w[1] - w[0]) // GLYPH_SIZE
            if cap <= 0:
                continue
            n = min(cap, glyph_count - gi)
            start = w[0]
            w[0] += n * GLYPH_SIZE
            placements.append(("glyphs", f"glyphs[{gi}:{gi + n}]", start, start + n * GLYPH_SIZE))
            for k in range(n):
                glyph_offsets.append(start + k * GLYPH_SIZE)
            gi += n
            placed = True
            break
        if not placed:
            fail(f"glyph {gi}/{glyph_count}에서 공간 부족")

    # 4. text: 고유 blob 단위 first-fit-decreasing
    blobs = {}
    for r in records:
        key = (r["target_offset"], r["translated_length"])
        blobs.setdefault(key, []).append(r["ordinal"])
    blob_place = {}
    for (toff, tlen), ordinals in sorted(blobs.items(), key=lambda kv: -kv[0][1]):
        at = alloc(tlen, ("text", f"text@{toff:06X}+{tlen}"))
        if at is None:
            fail(f"text blob {tlen}B (records {ordinals}) 공간 부족")
        blob_place[(toff, tlen)] = at

    # ---- 전수 검증 ----
    placements.sort(key=lambda p: p[2])
    for i in range(1, len(placements)):
        if placements[i][2] < placements[i - 1][3]:
            fail(f"placement overlap: {placements[i - 1]} vs {placements[i]}")
    region_set = []
    for s, e, _src in regions:
        region_set.append((s, e))
    for _a, name, s, e in placements:
        if s // BANK != (e - 1) // BANK:
            fail(f"{name}: bank crossing {s:#x}..{e:#x}")
        if not any(rs <= s and e <= re_ for rs, re_ in region_set):
            fail(f"{name}: outside candidate regions {s:#x}..{e:#x}")

    # ---- wire v2 index 직렬화 ----
    fmt_v1 = json.load(open(os.path.join(Z87_DIR, "field_dialogue_format.json"), encoding="utf-8"))
    hdr_struct = fmt_v1["header"]["struct"]
    index_bytes = bytearray()
    index_bytes += struct.pack(
        hdr_struct, b"ZTR2", 2, RECORD_SIZE, len(records), INDEX_HEADER, 0,
        0x0F1000, len(text_blob), glyph_count, BANK, gtab_at, 0)
    for r in sorted(records, key=lambda x: x["source_key"]):
        target = blob_place[(r["target_offset"], r["translated_length"])]
        index_bytes += r["source_key"].to_bytes(3, "little")
        index_bytes += target.to_bytes(3, "little")
        index_bytes += struct.pack("<HHBB", r["original_length"], r["translated_length"],
                                   r["kind_code"], r["flags"])
    if len(index_bytes) != index_size:
        fail("index serialization size mismatch")

    # ---- canary 계획 ----
    canary_ok = 0
    canary_blocked = 0
    canary_ranges = []
    for _a, _n, s, e in placements:
        cur = None
        for i in range(s, e):
            ok = cold[i] == 1 and reclaim[i] == 0
            if ok:
                canary_ok += 1
                if cur is None:
                    cur = i
            else:
                canary_blocked += 1
                if cur is not None:
                    canary_ranges.append((cur, i))
                    cur = None
        if cur is not None:
            canary_ranges.append((cur, e))

    total_placed = sum(e - s for _a, _n, s, e in placements)

    manifest = {
        "format": "ZIRIA-Z8-9-WIRE-V2-PLACEMENT",
        "version": 1,
        "inputs": {
            "coverage_manifest_status": cov["status"],
            "coverage_segments": cov["segments"],
            "records": 235,
            "text_blob_bytes": len(text_blob),
            "glyph_count": glyph_count,
        },
        "layout": {
            "index_at": index_at,
            "index_bytes": index_size,
            "glyph_table_at": gtab_at,
            "glyph_table_bytes": gtab_size,
            "glyph_fragments": [
                {"name": n, "start": s, "end": e}
                for a, n, s, e in placements if a == "glyphs"
            ],
            "text_blobs": len(blobs),
            "total_placed_bytes": total_placed,
        },
        "canary_plan": {
            "fillable_bytes": canary_ok,
            "blocked_bytes_reclaim_or_uncold": canary_blocked,
            "note": "blocked 바이트는 canary 게이트에서 검증되지 않는다. "
                    "reclaim 바이트는 redirect 적용 빌드에서만 사용 가능하다.",
            "ranges": [
                {"start": s, "end": e, "bytes": e - s} for s, e in canary_ranges
            ],
        },
        "placements": [
            {"asset": a, "name": n, "start": s, "end": e, "bytes": e - s,
             "bank": BANK_FIRST + s // BANK}
            for a, n, s, e in placements
        ],
        "index_sha256": hashlib.sha256(bytes(index_bytes)).hexdigest().upper(),
        "status": "PLACEMENT_PASS_PENDING_CANARY_AND_READER_HOOK",
        "disc_mutated": False,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "field_dialogue_index_v2.bin"), "wb") as f:
        f.write(index_bytes)
    with open(os.path.join(OUT_DIR, "placement_map.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("asset\tname\tstart\tend\tbytes\tbank\n")
        for a, n, s, e in placements:
            f.write(f"{a}\t{n}\t{s:06X}\t{e:06X}\t{e - s}\t{BANK_FIRST + s // BANK:02X}\n")
    with open(os.path.join(OUT_DIR, "canary_fill_ranges.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("start\tend\tbytes\n")
        for s, e in canary_ranges:
            f.write(f"{s:06X}\t{e:06X}\t{e - s}\n")
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    print(f"Z8.9c WIRE V2 PLACEMENT: {manifest['status']}")
    print(f"  index @ {index_at:06X} ({index_size} B, bank {BANK_FIRST + index_at // BANK:02X})")
    print(f"  glyph table @ {gtab_at:06X} ({gtab_size} B)")
    print(f"  glyph fragments: {sum(1 for a, *_ in placements if a == 'glyphs')}")
    print(f"  text blobs: {len(blobs)} (dedup), total placed {total_placed} B")
    print(f"  canary fillable {canary_ok} B / blocked {canary_blocked} B")


if __name__ == "__main__":
    main()
