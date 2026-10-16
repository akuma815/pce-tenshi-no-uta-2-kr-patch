#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제자리(in-place) 메시지 번역 띄어쓰기 적용: Kiwi 초안(translation/respace/inplace_kiwi_draft.json) + 수작업 교정(inplace_manual_fixes.py).
공백 외 변경 금지 검사 후 ziria_z8_text_entry_index.csv·master_text.csv 의 translation 을 갱신. 결과 사전 = translation/respace/inplace_respace_map.json.
빌더(b10)는 칸이 남으면 공백을 반칸 {~}(1B)로 넣고, 안 들어가면 공백을 뺀다."""
import csv, io, json, re, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]; RD = ROOT / "translation" / "respace"
spec = importlib.util.spec_from_file_location("fx", RD / "inplace_manual_fixes.py"); fx = importlib.util.module_from_spec(spec); spec.loader.exec_module(fx)
draft = json.loads((RD / "inplace_kiwi_draft.json").read_text(encoding="utf-8"))
mapping = {}
for old, new in draft:
    for a, b in fx.FIX:
        assert a.replace(" ", "") == b.replace(" ", ""), (a, b)
        new = new.replace(a, b)
    for a, b in fx.RULES: new = re.sub(a, b, new)
    assert new.replace(" ", "") == old.replace(" ", ""), old
    if new != old: mapping[old] = new
used = {a for a, b in fx.FIX if any(a in n for n in [d[1] for d in draft])}
print("unused manual fixes:", [a for a, b in fx.FIX if a not in used])
(RD / "inplace_respace_map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=0), encoding="utf-8")
for path, key, sep, enc in ((ROOT / "translation" / "ziria_z8_text_entry_index.csv", "translation", ",", "utf-8-sig"),):
    rows = list(csv.reader(io.open(path, encoding=enc, newline="")))
    ti = [h.lstrip("\ufeff") for h in rows[0]].index(key); n = 0
    for r in rows[1:]:
        if r[ti] in mapping: r[ti] = mapping[r[ti]]; n += 1
    with io.open(path, "w", encoding=enc, newline="") as f: csv.writer(f).writerows(rows)
    print(path.name, "rows updated", n)
mt = ROOT / "translation" / "full_extraction" / "master_text.csv"
rows = list(csv.reader(io.open(mt, encoding="utf-8", newline="")))
ti = [h.lstrip("\ufeff") for h in rows[0]].index("translation"); n = 0
for r in rows[1:]:
    if r[ti] in mapping: r[ti] = mapping[r[ti]]; n += 1
with io.open(mt, "w", encoding="utf-8", newline="") as f: csv.writer(f).writerows(rows)
print("master_text rows updated", n, "| texts", len(mapping))
