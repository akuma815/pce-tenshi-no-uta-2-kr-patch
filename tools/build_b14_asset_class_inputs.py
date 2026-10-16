#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""b14 — b10 이 보류했던 `asset_confirmed_short_event_text` 클래스(4,024행·고유 232)를
소비 경로별로 갈라 두 빌더의 입력으로 만든다 (2026-10-09).

근거: 같은 문장 `ライヒ草を見つけた。`(slot01) 는 b9 카드에서 이미 서브된다.
이 클래스가 빠진 이유는 분석기의 "자산 클러스터" 분류뿐이다.

판정 = **선행 바이트**:
  · 02/03/14 (인라인 opcode) → b9 보충 코퍼스(`b9_gap_supplement_source.tsv`)에 추가
    → 카드 서브(길이 캡 없음). `イベント０x` 류 디버그 표식은 제외.
  · 그 외(NUL 등 = 이름 테이블 항목) → b10 제자리 빌더 추가 대상
    (`translation/b14_inplace_extra_ids.txt`). 안 들어가는 행은 빌더가 fail-closed 로
    원문 유지 + worklist(짧춤 검토는 인간).

출력:
  translation/b9_gap_supplement_source.tsv (기존 행 보존 + 추가; 원본은 .pre_b14.bak)
  translation/b14_inplace_extra_ids.txt
  translation/b14_asset_class_split.tsv (판정 근거 전수)
"""
from __future__ import annotations

import csv
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
INDEX = ROOT / "translation" / "ziria_z8_text_entry_index.csv"
SUPP = ROOT / "translation" / "b9_gap_supplement_source.tsv"
EXTRA = ROOT / "translation" / "b14_inplace_extra_ids.txt"
SPLIT = ROOT / "translation" / "b14_asset_class_split.tsv"

SCENE_SECTORS = {290: 96, 386: 96, 482: 96, 578: 78, 674: 96, 770: 96,
                 866: 96, 962: 96, 1058: 83, 1154: 96, 1250: 96, 1346: 96,
                 1442: 96, 1538: 73, 1634: 96, 1730: 92, 1826: 96, 1922: 96,
                 2018: 82, 2114: 75, 2210: 76, 2306: 96, 2402: 96, 2498: 71,
                 2594: 71, 2690: 96, 2786: 69, 2882: 96, 2978: 94, 3074: 96,
                 3170: 96, 3266: 96, 3362: 96, 3458: 96, 3554: 84, 3650: 84,
                 3746: 96, 3842: 96, 3938: 96, 4034: 75, 4130: 96, 4226: 96,
                 4322: 96, 4418: 80, 4514: 82, 4610: 81, 4706: 81, 4802: 90,
                 4898: 76, 4994: 76, 5090: 84, 5186: 96, 5282: 96, 5378: 96}
DEBUG_RE = re.compile(r"^イベント[０-９0-9]+$")


def scene_of(off: int):
    c = [l for l, n in SCENE_SECTORS.items() if l * 2048 <= off < (l + n) * 2048]
    assert len(c) <= 1, (hex(off), c)
    return c[0] if c else None


def main() -> None:
    csv.field_size_limit(10 ** 7)
    iso = ISO.read_bytes()
    rows = list(csv.DictReader(INDEX.open(encoding="utf-8-sig", newline="")))
    cls = [r for r in rows if r["subcategory"] == "asset_confirmed_short_event_text"]

    existing_supp = list(csv.DictReader(SUPP.open(encoding="utf-8", newline=""),
                                        delimiter="\t"))
    existing_ids = {r["id"] for r in existing_supp}

    supp_rows, extra_ids, split = [], [], []
    stat = Counter()
    for r in cls:
        off = int(r["iso_offset"], 16)
        op = iso[off - 1]
        tr = (r["translation"] or "").strip()
        verdict, why = "", ""
        if not tr or r.get("same_as_original") == "yes":
            verdict, why = "skip", "untranslated"
        elif DEBUG_RE.match(r["original"]):
            verdict, why = "skip", "debug_marker"
        elif op in (0x02, 0x03, 0x14):
            lba = scene_of(off)
            if lba is None:
                verdict, why = "skip", "outside_scene_extent"
            elif r["id"] in existing_ids:
                verdict, why = "skip", "already_in_supplement"
            else:
                verdict, why = "card", f"opcode{op:02X}"
                supp_rows.append({"id": r["id"], "scene": str(lba),
                                  "consumer": "opcode02", "review_status": "index",
                                  "jp": r["original"], "ko": tr})
        else:
            verdict, why = "inplace", f"prev={op:02X}"
            extra_ids.append(r["id"])
        stat[(verdict, why.split("=")[0])] += 1
        split.append((r["id"], f"{op:02X}", verdict, why, r["raw_length"],
                      r["encoded_length"], r["original"], tr))

    bak = SUPP.with_suffix(".tsv.pre_b14.bak")
    if not bak.exists():
        shutil.copy2(SUPP, bak)
    with SUPP.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "scene", "consumer", "review_status", "jp", "ko"],
                           delimiter="\t", lineterminator="\n")
        w.writeheader()
        for row in existing_supp:
            w.writerow(row)
        for row in supp_rows:
            w.writerow(row)
    EXTRA.write_text("\n".join(extra_ids) + "\n", encoding="utf-8")
    with SPLIT.open("w", encoding="utf-8", newline="") as f:
        f.write("id\tprev\tverdict\twhy\traw_len\tenc_len\toriginal\ttranslation\n")
        for s in split:
            f.write("\t".join(str(x) for x in s) + "\n")
    print({"class_rows": len(cls), "card_rows_added": len(supp_rows),
           "card_unique": len({r['jp'] for r in supp_rows}),
           "inplace_rows": len(extra_ids),
           "inplace_unique": len({r['original'] for r in cls if r['id'] in set(extra_ids)}),
           "stats": dict(stat)})


if __name__ == "__main__":
    main()
