#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.11 — 전 영역(모든 텍스트 표면) 한국어 전환 가능성 감사.

목적: 필드 대사 창에 국한하지 않고, 게임의 모든 텍스트 표면이
"패키지 텍스트 창 + redirect + GETFNT 훅(+ 제자리 치환/타일 repaint)"
전략으로 수용 가능한지 슬롯·표면 단위로 판정한다.

판정 요소(슬롯별):
1. 전용 창: 두 55-entry 테이블의 다른 모든 extent와 겹치지 않는 섹터
   (동일 LBA 중복 엔트리는 하나의 extent로 본다).
2. 레이아웃 실측: master_text.csv의 슬롯 내 텍스트 레코드가 전용 창 안에
   있는 비율. 창 밖 레코드는 공유 섹터 텍스트로 별도 위험 목록에 올린다.
3. 수요: 컨테이너 요약의 번역 인코딩 바이트 + Z7 글리프 수×8B(8×8 잉크
   저장) + 인덱스 추정(레코드×10B+64B).
4. 공급 하한: 창 안 원문 레코드 raw 바이트 합(=redirect 후 회수 하한).
   공급 상한: 창 크기(482 실측 가용률 72.7%를 기준선으로 병기).

판정 등급:
  FIT_RECLAIM  수요 ≤ 회수 하한 (슬랙 없이도 성립)
  FIT_WINDOW   수요 ≤ 창×0.727 (482 실측 가용률)
  TIGHT        수요 ≤ 창
  OVER         수요 > 창
  NO_WINDOW    전용 창 < 4KB

비장면 표면(boot/system/engine 등)은 region·category별 저장 위치와
제자리 적합(fixed fit) 통계로 별도 표를 만든다.

이 감사는 원본을 수정하지 않는다.
"""

import csv
import json
import os
import re
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(ROOT, "translation", "ziria_z8_9_disc_reference_audit_manifest.json")
CONTAINERS = os.path.join(ROOT, "translation", "ziria_z8_text_container_summary.csv")
MASTER = os.path.join(ROOT, "translation", "full_extraction", "master_text.csv")
Z7 = os.path.join(ROOT, "translation", "ziria_z7_glyph_packages_manifest.json")

OUT_MANIFEST = os.path.join(ROOT, "translation", "ziria_z8_11_whole_surface_audit.json")
OUT_MATRIX = os.path.join(ROOT, "module_relink", "z8_11_whole_surface", "slot_matrix.tsv")
OUT_NONSCENE = os.path.join(ROOT, "module_relink", "z8_11_whole_surface", "nonscene_surfaces.tsv")

USABLE_RATIO = 26809 / 36864          # 482 실측 (cold 19,395 + reclaim 7,414) / 창 36,864
GLYPH_BYTES = 8                        # Galmuri8x8 잉크 8×8 = 8B/자 저장
INDEX_PER_ROW = 10
INDEX_HEADER = 64
MIN_WINDOW = 4096


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    audit = json.load(open(AUDIT, encoding="utf-8"))
    prim = [(e["lba"], e["lba"] + e["sector_count"]) for e in audit["static_references"]["primary_table"]]
    scen = [(e["entry"], e["lba"], e["sector_count"]) for e in audit["static_references"]["scene_table"]]

    # 동일 extent 중복 엔트리 그룹화
    extent_of = {}
    groups = collections.defaultdict(list)
    for ent, l, c in scen:
        extent_of[ent] = (l, l + c)
        groups[(l, l + c)].append(ent)

    def exclusive_segments(ent):
        l, e = extent_of[ent]
        segs = [(l, e)]
        others = list(prim)
        for (gl, ge), ents in groups.items():
            if (gl, ge) == (l, e):
                continue
            others.append((gl, ge))
        for a, b in others:
            out = []
            for s, t in segs:
                if b <= s or a >= t:
                    out.append((s, t))
                    continue
                if s < a:
                    out.append((s, a))
                if b < t:
                    out.append((b, t))
            segs = out
        return segs

    # 컨테이너 요약: 슬롯별/비장면별 수요
    slot_demand = collections.defaultdict(lambda: {"rows": 0, "orig": 0, "trans": 0,
                                                   "fixed_fit": 0, "reloc": 0})
    nonscene = collections.defaultdict(lambda: {"rows": 0, "orig": 0, "trans": 0,
                                                "fixed_fit": 0, "reloc": 0, "families": set()})
    for r in csv.DictReader(open(CONTAINERS, encoding="utf-8-sig")):
        mm = re.match(r"scene\.slot(\d+)$", r["storage_module"])
        tgt = slot_demand[int(mm.group(1))] if mm else nonscene[r["storage_module"]]
        tgt["rows"] += int(r["row_count"])
        tgt["orig"] += int(r["original_bytes"])
        tgt["trans"] += int(r["translated_bytes_before_dedup"])
        tgt["fixed_fit"] += int(r["fixed_length_candidates"])
        tgt["reloc"] += int(r["relocation_required_by_length"])
        if not mm:
            tgt["families"].add(r["family"])

    # Z7 글리프: 모듈별 합(공유 core 중복 포함 → 보수적 상한)
    z7 = json.load(open(Z7, encoding="utf-8"))
    slot_glyphs = collections.defaultdict(int)
    nonscene_glyphs = collections.defaultdict(int)
    for p in z7["packages"]:
        mm = re.match(r"scene\.slot(\d+)$", p["module_id"])
        if mm:
            slot_glyphs[int(mm.group(1))] += p["glyph_count"]
        else:
            nonscene_glyphs[p["module_id"]] += p["glyph_count"]

    # master_text: 슬롯 내 레코드 위치 실측
    slot_records = collections.defaultdict(list)   # ent -> [(sector, rawlen)]
    nonscene_regions = collections.defaultdict(lambda: collections.Counter())
    for r in csv.DictReader(open(MASTER, encoding="utf-8-sig")):
        try:
            sector = int(r["sector"])
        except ValueError:
            continue
        rawlen = len(r["raw_hex"]) // 2 if r["raw_hex"] else 0
        placed = False
        for ent, l, c in scen:
            if l <= sector < l + c:
                slot_records[ent].append((sector, rawlen))
                placed = True
                break
        if not placed:
            nonscene_regions[r["region"] or "unknown"][r["category"]] += 1

    # 슬롯 매트릭스
    rows_out = []
    class_count = collections.Counter()
    hazard_slots = []
    seen_extents = set()
    for ent, l, c in scen:
        key = extent_of[ent]
        twin = [x for x in groups[key] if x != ent]
        if key in seen_extents:
            rows_out.append({
                "slot": ent, "lba": l, "verdict": "TWIN_OF_" + str(min(groups[key])),
            })
            continue
        seen_extents.add(key)

        segs = exclusive_segments(ent)
        excl = sum(e - s for s, e in segs) * 2048
        d = slot_demand.get(ent, {"rows": 0, "orig": 0, "trans": 0, "fixed_fit": 0, "reloc": 0})
        # twin 슬롯 수요 합산
        for t in twin:
            td = slot_demand.get(t)
            if td:
                for k2 in ("rows", "orig", "trans", "fixed_fit", "reloc"):
                    d[k2] += td[k2]
        gl = (slot_glyphs.get(ent, 0) + sum(slot_glyphs.get(t, 0) for t in twin)) * GLYPH_BYTES
        need = d["trans"] + gl + d["rows"] * INDEX_PER_ROW + INDEX_HEADER

        recs = slot_records.get(ent, []) + sum((slot_records.get(t, []) for t in twin), [])
        in_win = [x for x in recs if any(s <= x[0] < e for s, e in segs)]
        reclaim_lower = sum(x[1] for x in in_win)
        out_win = len(recs) - len(in_win)

        if excl < MIN_WINDOW:
            verdict = "NO_WINDOW"
        elif need <= reclaim_lower:
            verdict = "FIT_RECLAIM"
        elif need <= excl * USABLE_RATIO:
            verdict = "FIT_WINDOW"
        elif need <= excl:
            verdict = "TIGHT"
        else:
            verdict = "OVER"
        class_count[verdict] += 1
        if verdict in ("NO_WINDOW", "OVER"):
            hazard_slots.append(ent)
        if out_win:
            hazard_note = f"{out_win} records outside exclusive window"
        else:
            hazard_note = ""
        rows_out.append({
            "slot": ent, "lba": l, "sectors": c,
            "exclusive_bytes": excl,
            "window_segments": [[s, e] for s, e in segs],
            "rows": d["rows"], "translated_bytes": d["trans"],
            "glyph_bytes": gl, "need_bytes": need,
            "reclaim_lower_bytes": reclaim_lower,
            "records_in_window": len(in_win), "records_outside_window": out_win,
            "verdict": verdict, "note": hazard_note,
        })

    # 비장면 표면 표
    nonscene_rows = []
    for mod, d in sorted(nonscene.items()):
        nonscene_rows.append({
            "storage_module": mod,
            "families": sorted(d["families"]),
            "rows": d["rows"], "original_bytes": d["orig"], "translated_bytes": d["trans"],
            "fixed_fit_rows": d["fixed_fit"], "relocation_rows": d["reloc"],
            "glyph_count": nonscene_glyphs.get(mod, 0),
            "strategy": ("in_place_fixed" if d["reloc"] == 0 else "needs_relocation_audit"),
        })

    outside_total = sum(r.get("records_outside_window", 0) for r in rows_out if isinstance(r.get("records_outside_window"), int))

    status_parts = []
    if class_count["OVER"] or class_count["NO_WINDOW"]:
        status_parts.append(f"UNRESOLVED_SLOTS_{class_count['OVER'] + class_count['NO_WINDOW']}")
    if any(r["strategy"] == "needs_relocation_audit" for r in nonscene_rows):
        status_parts.append("NONSCENE_RELOCATION_AUDIT_OPEN")
    if outside_total:
        status_parts.append(f"SHARED_SECTOR_TEXT_{outside_total}_RECORDS")
    status = "WHOLE_SURFACE_" + ("_".join(status_parts) if status_parts else "FEASIBLE")

    manifest = {
        "format": "ZIRIA-Z8-11-WHOLE-SURFACE-AUDIT",
        "version": 1,
        "assumptions": {
            "usable_ratio_calibration": "slot02(482) 실측 26,809/36,864",
            "glyph_bytes_per_char": GLYPH_BYTES,
            "index_bytes_per_row": INDEX_PER_ROW,
            "glyph_note": "모듈 내 family 합산(공유 core 중복 포함, 보수적 상한)",
        },
        "slot_matrix": rows_out,
        "verdict_counts": dict(class_count),
        "hazard_slots": hazard_slots,
        "records_outside_exclusive_window_total": outside_total,
        "nonscene_surfaces": nonscene_rows,
        "nonscene_record_regions": {
            k: dict(v) for k, v in sorted(nonscene_regions.items())
        },
        "status": status,
        "disc_mutated": False,
    }

    os.makedirs(os.path.dirname(OUT_MATRIX), exist_ok=True)
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(OUT_MATRIX, "w", encoding="utf-8", newline="\n") as f:
        cols = ["slot", "lba", "exclusive_bytes", "rows", "translated_bytes", "glyph_bytes",
                "need_bytes", "reclaim_lower_bytes", "records_in_window",
                "records_outside_window", "verdict", "note"]
        f.write("\t".join(cols) + "\n")
        for r in rows_out:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")
    with open(OUT_NONSCENE, "w", encoding="utf-8", newline="\n") as f:
        cols = ["storage_module", "rows", "original_bytes", "translated_bytes",
                "fixed_fit_rows", "relocation_rows", "glyph_count", "strategy"]
        f.write("\t".join(cols) + "\n")
        for r in nonscene_rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")

    print(f"Z8.11 WHOLE SURFACE AUDIT: {status}")
    print("  slot verdicts:", dict(class_count))
    print("  hazard slots:", hazard_slots)
    print("  records outside exclusive windows:", outside_total)
    print("  non-scene surfaces:", len(nonscene_rows))
    for r in nonscene_rows:
        print(f"    {r['storage_module']:24s} rows={r['rows']:4d} trans={r['translated_bytes']:6d}B "
              f"reloc={r['relocation_rows']:4d} glyphs={r['glyph_count']:3d} -> {r['strategy']}")


if __name__ == "__main__":
    main()
