#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지명 배너 띄어쓰기 적용 (translation/respace/location_names.py). 앞 {~} 패딩을 공백 수만큼 줄이고, 공백은 전각 공백 문자(　)로 쓴다
(location_names 는 SPACE_SUBCATS 밖이라 반각 공백이 인코딩에서 지워진다)."""
import csv, io, re, importlib.util
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ln", ROOT / "translation" / "respace" / "location_names.py"); ln = importlib.util.module_from_spec(spec); spec.loader.exec_module(ln)
def convert(t):
    m = re.match(r"^((?:\{~\})*)(.*)$", t); pad, body = m.group(1), m.group(2)
    key = body.replace("　", " ")
    if key not in ln.L: return t
    new = ln.L[key]; n_sp = new.count(" ") - key.count(" ")
    pads = pad.count("{~}"); pads = max(0, pads - max(0, n_sp)) if n_sp > 0 else pads
    return "{~}" * pads + new.replace(" ", "　")
for path, enc in ((ROOT / "translation" / "ziria_z8_text_entry_index.csv", "utf-8-sig"), (ROOT / "translation" / "full_extraction" / "master_text.csv", "utf-8")):
    rows = list(csv.reader(io.open(path, encoding=enc, newline="")))
    H = [h.lstrip("\ufeff") for h in rows[0]]; ti, si = H.index("translation"), H.index("subcategory"); n = 0
    for r in rows[1:]:
        if r[si] == "location_names":
            nt = convert(r[ti])
            if nt != r[ti]: r[ti] = nt; n += 1
    with io.open(path, "w", encoding=enc, newline="") as f: csv.writer(f).writerows(rows)
    print(path.name, "rows", n)
