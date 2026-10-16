#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""b3 맵 OLD_FALLBACK 대사의 띄어쓰기 수작업 교정 적용 (translation/respace/edits.py + source.json).
안전장치: 교정 전후 텍스트에서 공백을 모두 지운 결과가 같아야 한다(공백 외 글자 변경 금지). 모든 치환 대상 문자열이 실제로 있어야 한다.
결과 사전 translation/respace/b3_respace_map.json(옛 텍스트 → 새 텍스트)을 저장하고 맵의 같은 텍스트 행 전부에 적용. b3 맵 재생성 후 재실행."""
import csv, io, json, sys, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "translation" / "btrack_b3_translation_map.tsv"
RD = ROOT / "translation" / "respace"
spec = importlib.util.spec_from_file_location("edits", RD / "edits.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
src = json.loads((RD / "source.json").read_text(encoding="utf-8"))["texts"]
mapping = {}
for i, reps in mod.E.items():
    old = src[i]; new = old
    for a, b in reps:
        assert a in new, f"#{i}: 없음 {a!r}"
        assert a.replace(" ", "") == b.replace(" ", ""), f"#{i}: 공백 외 변경 {a!r}→{b!r}"
        new = new.replace(a, b)
    assert old.replace(" ", "") == new.replace(" ", "")
    mapping[old] = new
(RD / "b3_respace_map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
rows = list(csv.reader(io.open(MAP, encoding="utf-8", newline=""), delimiter="\t"))
hit = []
for r in rows[1:]:
    if r[5] in mapping: r[5] = mapping[r[5]]; hit.append(r[0])
with io.open(MAP, "w", encoding="utf-8", newline="") as f: csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
print("texts edited", len(mapping), "rows updated", len(hit)); print(json.dumps(hit))
