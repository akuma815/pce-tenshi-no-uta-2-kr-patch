#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""b3 맵: Switch 번역에서 무언 페이지(본문 「・・・」)의 화자명이 「・・・」로 바뀐 것을 원문 화자의 한국어 이름으로 되돌린다 (2026-10-10 사용자 보고).
원문 JP 화자 헤더 목록과 KO 화자 헤더 목록을 순서대로 맞춰(개수 같을 때만) 점만 있는 KO 화자를 NAME 표로 치환. b3 맵 재생성 후 재실행."""
import csv, io, re
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "translation" / "btrack_b3_translation_map.tsv"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
BS = chr(92)
NAME = {"ティアラ": "티아라", "ローブの女": "로브를 쓴 여자", "ラミアム": "라미암", "地底人男": "지저인 남자", "地底人女": "지저인 여자",
        "シオン": "시온", "ラファエルの声": "라파엘의 목소리", "フェイト": "페이트", "ケアル": "케알"}
SP = re.compile(re.escape("{#5}") + "([^{}" + re.escape(BS) + "]{1,20}?)([：:])" + re.escape(BS + "n{#1}"))
DOTS = re.compile(r"[^가-힣A-Za-z0-9]+")   # 한글·영숫자가 없는 화자 = 구두점만(「・・・」「！？」「？？？」 등)
master = {r[0]: r for r in csv.reader(io.open(MASTER, encoding="utf-8", newline=""))}
OI = [h.lstrip("\ufeff") for h in next(iter(master.values()))].index("original")
rows = list(csv.reader(io.open(MAP, encoding="utf-8", newline=""), delimiter="\t"))
fixed, skipped = [], []
for r in rows[1:]:
    ko_heads = list(SP.finditer(r[5]))
    if not any(DOTS.fullmatch(m.group(1)) for m in ko_heads): continue
    jp = SP.findall(master.get(r[0], [""] * 20)[OI])
    if len(jp) != len(ko_heads): skipped.append((r[0], "count")); continue
    s = r[5]
    for m, (jn, _) in reversed(list(zip(ko_heads, jp))):
        if DOTS.fullmatch(m.group(1)):
            if jn not in NAME: skipped.append((r[0], jn)); continue
            s = s[:m.start(1)] + NAME[jn] + s[m.end(1):]
    if s != r[5]: r[5] = s; fixed.append(r[0])
with io.open(MAP, "w", encoding="utf-8", newline="") as f: csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
print("fixed", len(fixed), fixed); print("skipped", skipped)
