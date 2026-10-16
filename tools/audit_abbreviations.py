#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공간 때문에 줄어든 표기 전수 조사 (2026-10-11 사용자 요청).

입력 = 제자리 빌더가 남기는 행별 최종 문구 `translation/btrack_<tag>_menu_final_text.json`
(B10_OUT_TAG=<tag> 로 빌더를 돌리면 생성; path = inplace/arena/reloc) + 손으로 쓴 짧은 표(미인덱스 전투 메시지).
전체 번역(인덱스 translation, 없으면 master_text) 과 비교 — 공백·전각/반각·조사 마커 차이는 무시.
출력: translation/abbreviation_audit_<tag>.tsv (kind = 줄임 / 다른표현)
"""
from __future__ import annotations
import collections, csv, io, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
tag = sys.argv[1]
csv.field_size_limit(10 ** 7)
BS = chr(92)


def ns(t: str) -> str:
    t = (t or "").replace("{~}", "")
    for a, b in (("！", "!"), ("？", "?"), ("（", "("), ("）", ")"), ("ＨＰ", "HP"), ("ＭＰ", "MP"), ("Ｇ", "G"),
                 ("．", "."), ("：", ":"), ("、", ","), ("，", ","), (BS + "n", ""), (BS + "p", ""), ("　", "")):
        t = t.replace(a, b)
    t = "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" or "Ａ" <= c <= "Ｚ" else c for c in t)
    return re.sub(r"\s", "", t)


def main() -> None:
    f = json.load(open(ROOT / "translation" / f"btrack_{tag}_menu_final_text.json", encoding="utf-8"))
    mt = list(csv.reader(io.open(ROOT / "translation" / "full_extraction" / "master_text.csv", encoding="utf-8", newline="")))
    h = {x.lstrip("﻿"): i for i, x in enumerate(mt[0])}
    master = {r[0]: r[h["translation"]] for r in mt[1:]}
    groups = collections.defaultdict(list)
    for k, v in f.items():
        full = v["translation"] or master.get(k, "")
        if not full:
            continue
        a, b = ns(v["ko"]), ns(full)
        if a == b:
            continue
        kind = "줄임" if len(a) < len(b) else "다른표현"
        groups[(kind, v["subcategory"], v["original"], full, v["ko"])].append(k)
    rows = sorted(groups.items(), key=lambda kv: kv[0])
    out = ROOT / "translation" / f"abbreviation_audit_{tag}.tsv"
    with io.open(out, "w", encoding="utf-8", newline="") as fo:
        w = csv.writer(fo, delimiter="\t", lineterminator="\n")
        w.writerow(["kind", "subcategory", "copies", "original", "full_translation", "in_game", "ids"])
        for (kind, sub, o, full, ko), ids in rows:
            w.writerow([kind, sub, len(ids), o, full, ko, ",".join(ids[:5])])
    print(out.name, "unique", len(rows), collections.Counter((k[0], k[1]) for k, _ in rows).most_common())


if __name__ == "__main__":
    main()
