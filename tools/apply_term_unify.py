#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이름 표기 통일(translation/respace/term_unify.py) 적용 (2026-10-11).

  · b3 맵(대사): 원문(master)에 그 이름이 나오는 레코드에서 대사 변형 → 통일 표기, 뒤 조사(을/를·은/는·이/가·와/과·으로/로)를 받침에 맞춤.
  · 카드 보충 원천 b9_gap_supplement_source.tsv: 같은 규칙(원문 열 4, 번역 열 5).
  · 제자리 색인 ziria_z8_text_entry_index.csv(번역 열): 같은 규칙 + MENU 치환, b10_menu_overrides.tsv 짧은 폴백(OVERRIDES).
사용: python -X utf8 tools/apply_term_unify.py [b3|all]   (apply_b3_manual_fixes.py 가 b3 를 자동 호출)
"""
from __future__ import annotations
import csv, importlib.util, io, re, sys
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "translation"
spec = importlib.util.spec_from_file_location("tu", T / "respace" / "term_unify.py"); tu = importlib.util.module_from_spec(spec); spec.loader.exec_module(tu)

BS = chr(92)
GAP = r"(?:\s|" + re.escape(BS) + r"n)*"


def batchim(ch: str) -> int:
    o = ord(ch) - 0xAC00
    return -1 if not (0 <= o < 11172) else o % 28      # -1 = 한글 아님, 0 = 받침 없음, 8 = ㄹ


def _josa(rest: str, tgt_b: int, var_b: int) -> str:
    """rest = 통일 표기 바로 뒤 문자열. 조사를 통일 표기의 받침에 맞춘다."""
    has = tgt_b > 0
    def nxt(i):
        return rest[i] if i < len(rest) else ""
    end_ok = lambda c: not c or batchim(c) < 0       # 조사 뒤가 한글이 아님(공백·문장부호·제어)
    if rest.startswith("으로") or (rest.startswith("로") and not rest.startswith("로서")):
        core = rest[2:] if rest.startswith("으로") else rest[1:]
        return ("으로" if has and tgt_b != 8 else "로") + core
    c0, c1 = nxt(0), nxt(1)
    if not c0:
        return rest
    if c0 in "을를":
        return ("을" if has else "를") + rest[1:]
    if c0 in "은는" and end_ok(c1):
        return ("은" if has else "는") + rest[1:]
    if c0 in "와과" and end_ok(c1):
        return ("과" if has else "와") + rest[1:]
    if c0 == "가" and end_ok(c1) and has:
        return "이" + rest[1:]
    if c0 == "이" and end_ok(c1) and not has:
        return "가" + rest[1:]
    if (var_b > 0) != has:                            # 서술격 조사(이다/이야/이라…)
        if c0 == "이" and c1 and c1 in "다야라란여잖지네었" and not has:
            return rest[1:]
        if has and c0 in "다야라란여" and var_b == 0:
            return "이" + rest
    return rest


def _rx(variant: str):
    if variant.startswith("re:"):                     # (2026-10-11) 정규식 변형 — 통일 표기가 변형을 포함할 때(키나리스 항 ⊂ 키나리스 항구)
        return re.compile(r"(?<![가-힣])" + variant[3:])
    chars = [re.escape(c) for c in variant if not c.isspace()]
    return re.compile(r"(?<![가-힣])" + GAP.join(chars))


RULES = [(jp, [_rx(v) for v in vs], tgt, [v for v in vs]) for jp, vs, tgt in tu.ENTRIES]


DOTS = re.compile(r"\.{2,}")


def unify(text: str, jp: str | None) -> str:
    # (2026-10-11) ASCII 말줄임 「...」 → 「・・・」(같은 개수). 인코더가 ASCII 마침표를 전각 「．」로 올려 「．．．」로 찍히던 것 — 원문 표기는 ・・・, 바이트 길이 같음
    text = DOTS.sub(lambda m: "・" * len(m.group(0)), text)
    for name, rxs, tgt, vs in RULES:
        if name and (not jp or name not in jp):
            continue
        tb = batchim(tgt[-1])
        for rx, v in zip(rxs, vs):
            vb = batchim(v[-1]) if not v.startswith("re:") else tb
            pos = 0
            while True:
                m = rx.search(text, pos)
                if not m:
                    break
                head, rest = text[:m.start()] + tgt, text[m.end():]
                text = head + _josa(rest, tb, vb)
                pos = len(head)
    return text


def apply_b3(rows_path=T / "btrack_b3_translation_map.tsv"):
    import csv as _c
    master = {r[0]: r[11] for r in _c.reader(io.open(T / "full_extraction" / "master_text.csv", encoding="utf-8", newline="")) if len(r) > 11}
    rows = list(_c.reader(io.open(rows_path, encoding="utf-8", newline=""), delimiter="\t"))
    ch = []
    for r in rows[1:]:
        new = unify(r[5], master.get(r[0], ""))
        if new != r[5]:
            r[5] = new; ch.append(r[0])
    with io.open(rows_path, "w", encoding="utf-8", newline="") as f:
        _c.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
    return ch


def apply_sup():
    p = T / "b9_gap_supplement_source.tsv"
    rows = list(csv.reader(io.open(p, encoding="utf-8", newline=""), delimiter="\t"))
    ch = []
    for r in rows[1:]:
        if len(r) > 5:
            new = unify(r[5], r[4])
            if new != r[5]:
                r[5] = new; ch.append(r[0])
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
    return ch


def apply_index():
    p = T / "ziria_z8_text_entry_index.csv"
    raw = p.read_bytes().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw, newline="")))
    h = rows[0]; io_, it = h.index("original"), h.index("translation")
    isc = h.index("subcategory")
    ch = []
    for r in rows[1:]:
        t = r[it]
        new = unify(t, r[io_])
        if r[isc] == "location_names":            # 지명 배너는 반각 공백이 인코딩에서 지워진다 → 전각 공백(apply_location_spacing 과 같은 규칙)
            new = new.replace(" ", "　")
        for jp, a, b in tu.MENU:
            if jp in r[io_]:
                new = new.replace(a, b)
        if new != t:
            r[it] = new; ch.append((r[0], r[io_], t, new))
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\r\n" if "\r\n" in raw[:500] else "\n").writerows(rows)
    p.write_bytes(("﻿" if p.read_bytes()[:3] == b"\xef\xbb\xbf" else "").encode("utf-8") + buf.getvalue().encode("utf-8"))
    po = T / "b10_menu_overrides.tsv"
    orows = list(csv.reader(io.open(po, encoding="utf-8", newline=""), delimiter="\t"))
    for r in orows[1:]:
        if len(r) > 2 and DOTS.search(r[2]):
            r[2] = DOTS.sub(lambda m: "・" * len(m.group(0)), r[2])
        if len(r) > 2 and r[0] == "orig" and r[1] in tu.OVERRIDES and r[2] != tu.OVERRIDES[r[1]]:
            ch.append(("override", r[1], r[2], tu.OVERRIDES[r[1]])); r[2] = tu.OVERRIDES[r[1]]
    with io.open(po, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(orows)
    return ch


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    c = apply_b3(); print("b3", len(c))
    if what == "all":
        s = apply_sup(); print("supplement", len(s), s)
        i = apply_index(); print("index/overrides", len(i))
        for x in i:
            print("  ", x)
