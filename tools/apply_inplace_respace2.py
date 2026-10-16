#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제자리 메시지 띄어쓰기 2차: translation/respace/inplace_round2_filtered.json(Kiwi 추가 공백 중 6자 이상 무공백 구간 분할 + {%s}/{%d} 뒤 조사 분리만)
+ 1차·2차 수작업 교정 → 인덱스·master translation 갱신. 공백만 바뀌는지 검사."""
import csv, io, json, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]; RD = ROOT / "translation" / "respace"
def load(name):
    spec = importlib.util.spec_from_file_location(name, RD / f"{name}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
FIX = load("inplace_manual_fixes").FIX + load("inplace_manual_fixes2").FIX
mapping = {}
for old, new in json.loads((RD / "inplace_round2_filtered.json").read_text(encoding="utf-8")):
    for a, b in FIX:
        assert a.replace(" ", "") == b.replace(" ", ""), (a, b)
        new = new.replace(a, b)
    assert new.replace(" ", "") == old.replace(" ", ""), old
    if new != old: mapping[old] = new
(RD / "inplace_respace_map2.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=0), encoding="utf-8")
for path, enc in ((ROOT / "translation" / "ziria_z8_text_entry_index.csv", "utf-8-sig"), (ROOT / "translation" / "full_extraction" / "master_text.csv", "utf-8")):
    rows = list(csv.reader(io.open(path, encoding=enc, newline="")))
    ti = [h.lstrip("\ufeff") for h in rows[0]].index("translation"); n = 0
    for r in rows[1:]:
        if r[ti] in mapping: r[ti] = mapping[r[ti]]; n += 1
    with io.open(path, "w", encoding=enc, newline="") as f: csv.writer(f).writerows(rows)
    print(path.name, "rows", n)
print("texts", len(mapping))
