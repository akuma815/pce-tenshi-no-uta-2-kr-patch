#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translation/respace/b3_manual_fixes.py 를 b3 맵에 적용(개별 + 전역 치환). 각 개별 항목은 반드시 한 번 이상 맞아야 한다. b3 맵 재생성 후 재실행."""
import csv, io, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]; MAP = ROOT / "translation" / "btrack_b3_translation_map.tsv"
spec = importlib.util.spec_from_file_location("mf", ROOT / "translation" / "respace" / "b3_manual_fixes.py"); mf = importlib.util.module_from_spec(spec); spec.loader.exec_module(mf)
rows = list(csv.reader(io.open(MAP, encoding="utf-8", newline=""), delimiter="\t")); changed = []
for r in rows[1:]:
    t = r[5]
    for a, b in mf.F.get(r[0], []):
        if a in t: t = t.replace(a, b)
    for a, b in mf.GLOBAL: t = t.replace(a, b)
    if t != r[5]: r[5] = t; changed.append(r[0])
missing = [i for i, reps in mf.F.items() if i not in changed]
with io.open(MAP, "w", encoding="utf-8", newline="") as f: csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
print("changed", len(changed), changed, "| unmatched ids:", missing)
# (2026-10-11) 이름 표기 통일표(translation/respace/term_unify.py)를 b3 맵에 이어서 적용 — b3 맵을 재생성해도 통일이 유지되도록
import sys as _sys; _sys.path.insert(0, str(ROOT / "tools"))
import apply_term_unify as _tu
print("term_unify b3 changed", len(_tu.apply_b3()))
