#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translation/respace/inplace_fit_edits.py 의 문구 조정을 ziria_z8 인덱스·master_text translation 에 적용 (공백 넣을 바이트 확보용)."""
import csv, io, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fe", ROOT / "translation" / "respace" / "inplace_fit_edits.py"); fe = importlib.util.module_from_spec(spec); spec.loader.exec_module(fe)
for path, enc in ((ROOT / "translation" / "ziria_z8_text_entry_index.csv", "utf-8-sig"), (ROOT / "translation" / "full_extraction" / "master_text.csv", "utf-8")):
    rows = list(csv.reader(io.open(path, encoding=enc, newline="")))
    ti = [h.lstrip("\ufeff") for h in rows[0]].index("translation"); n = 0; hit = set()
    for r in rows[1:]:
        if r[ti] in fe.E: hit.add(r[ti]); r[ti] = fe.E[r[ti]]; n += 1
    with io.open(path, "w", encoding=enc, newline="") as f: csv.writer(f).writerows(rows)
    print(path.name, "rows", n, "| unmatched keys:", [k for k in fe.E if k not in hit])
