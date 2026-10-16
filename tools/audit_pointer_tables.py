#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빌드 bin 의 제자리 이름/메뉴 포인터 테이블 전 항목을 디코드해 번역문(또는 원문)과 비교 (2026-10-10, 가짜 테이블 사건 이후 상시 점검용).
사용: python -X utf8 tools/audit_pointer_tables.py <빌드태그>   불일치가 몬스터 오버라이드(날비늘·허수아비) 외에 있으면 조사."""
import csv, io, json, re, sys
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]; tag = sys.argv[1]; sys.argv = ["x"]; sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_hook_build import T2
from build_btrack_b10_menu_inplace import find_pointer_tables
iso = open(ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin", "rb").read()[T2:]
bb = open(ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{tag}.bin", "rb").read()[T2:]
asg = json.load(open(ROOT / "translation" / "btrack_slot_assignment.json", encoding="utf-8"))["assignment"]
rev = {bytes.fromhex(e["sjis"]): ch for ch, e in asg.items()}
one = {int(k, 16): v["ch"] for k, v in json.load(open(ROOT / "translation" / "b26_onebyte_map.json", encoding="utf-8"))["map"].items()}
def dec(b):
    out = []; i = 0
    while i < len(b) and b[i] != 0:
        c = b[i]
        if c in one: out.append(one[c]); i += 1; continue
        if c == 0x7E: out.append(" "); i += 1; continue
        if c >= 0x80 and i + 1 < len(b): k = b[i:i + 2]; out.append(" " if k == b"\x81\x40" else (rev.get(k) or k.decode("shift_jis", "replace"))); i += 2
        else: out.append(f"<{c:02X}>"); i += 1
    return "".join(out)
def norm(s): return re.sub(r"\s|　", "", s.replace("{~}", "").replace("<7E>", "")).replace("（", "(").replace("）", ")")
rows = [r for r in csv.DictReader(io.open(ROOT / "translation" / "ziria_z8_text_entry_index.csv", encoding="utf-8-sig", newline="")) if r["category"] == "menu_data"]
bad = []; total = 0
allruns = []
for sub in sorted({r["subcategory"] for r in rows}):
    grp = sorted([r for r in rows if r["subcategory"] == sub], key=lambda r: int(r["iso_offset"], 16))
    runs, cur = [], [grp[0]]
    for a, b in zip(grp, grp[1:]):
        if int(a["iso_offset"], 16) + int(a["raw_length"]) == int(b["iso_offset"], 16): cur.append(b)
        else: runs.append(cur); cur = [b]
    runs.append(cur)
    for run in runs:
        if len(run) < 4: continue
        offs = [int(r["iso_offset"], 16) for r in run]
        allruns.append((sub, run, offs, find_pointer_tables(iso, offs)))
spans = [(k, t, t + 2 * len(run)) for k, (_, run, _, tabs) in enumerate(allruns) for t, _ in tabs]
for k, (sub, run, offs, tabs) in enumerate(allruns):
    n = len(run)
    for t, base in tabs:
        if any(j != k and t < s1 and s0 < t + 2 * n and (s1 - s0) > 2 * n for j, s0, s1 in spans): continue   # 빌더와 같은 가짜 테이블 기각
        if True:
            for i, r in enumerate(run):
                pn = bb[t + 2 * i] | (bb[t + 2 * i + 1] << 8); sn = offs[0] + (pn - base); total += 1
                got = dec(bb[sn:sn + 40]) if 0 <= sn < len(bb) else "?"; tr = r["translation"] or r["original"]
                if norm(got) != norm(tr) and norm(got) != norm(r["original"]): bad.append((sub, r["id"], hex(t), i, got[:14], tr[:14]))
from collections import Counter
print("entries", total, "mismatch", len(bad)); print(Counter((b[0], b[5], b[4]) for b in bad).most_common(20))
