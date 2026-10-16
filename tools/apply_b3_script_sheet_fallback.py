#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""b3 번역 맵의 OLD_FALLBACK(구 고정길이 번역 = 띄어쓰기를 지워 원문 바이트에 맞춘 축약본)을
script_sheet.tsv(원본 xlsx 의 같은 레코드 전체 번역, 띄어쓰기 정상)로 교체한다. (2026-10-10 사용자 보고: 대사 띄어쓰기)

카드 서브(b9) 이후 대사 길이 제한이 없으므로 축약본을 쓸 이유가 없다. 안전 조건(하나라도 어긋나면 그 레코드는 건너뜀):
  - master 원문의 제어가 {#5}/{#1}/\n/\p 뿐 (서식 토큰 {%x}·{0B} 등이 있는 레코드는 제외)
  - script_sheet 번역에 '{' 가 없음
  - 페이지 수 일치 (script_sheet 페이지 구분 = \c, \c\n, \c\p)
  - 페이지별 화자 헤더 유무 일치: master `{#5}이름：\n{#1}` ↔ script `이름:\n`
출력: 같은 맵 파일을 갱신(상태 SS_FULL), 보고서 translation/b3_ss_fallback_report.tsv. 백업은 실행 전에 따로 뜰 것.
b3 맵을 build_btrack_b3_translation_map.py 로 재생성했다면 이 스크립트를 다시 돌려야 한다.
"""
import csv, io, re, sys
from pathlib import Path
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "translation" / "btrack_b3_translation_map.tsv"
SS = ROOT / "translation" / "script_sheet.tsv"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
REPORT = ROOT / "translation" / "b3_ss_fallback_report.tsv"
BS = chr(92); BSN = BS + "n"; BSP = BS + "p"
ALLOWED = re.compile(r"\{#[15]\}|" + re.escape(BSN) + "|" + re.escape(BSP))
SPK_M = re.compile(r"^\{#5\}([^{}" + re.escape(BS) + r"]{1,16})[：:]" + re.escape(BSN) + r"\{#1\}")
SPK_S = re.compile(r"^([^{}" + re.escape(BS) + r"\n]{1,16}?)[：:]" + re.escape(BSN))
PAGE_S = re.compile(re.escape(BS) + "c(?:" + re.escape(BSN) + "|" + re.escape(BSP) + ")?|" + re.escape(BSP))


def convert(orig: str, ko: str):
    if "{" in ko: return None, "ss_has_token"
    # 두 번째 표기: 화자 앞 페이지 구분이 `
#5이름：
#1` (중괄호 없는 색 코드)
    ko = ko.replace(BSN + "#5", BS + "c#5")
    if ko.startswith("#5"): ko = ko  # 첫 페이지 화자
    ko = re.sub(r"(^|" + re.escape(BS) + r"c)#5", lambda m: m.group(1), ko)
    ko = ko.replace(BSN + "#1", BSN)
    rest = ALLOWED.sub("", orig)
    if re.search(r"\{[^}]*\}", rest): return None, "master_has_format_token"
    mp = orig.split(BSP)
    sp = [p for p in PAGE_S.split(ko)]
    while sp and not sp[-1].strip(): sp.pop()
    if len(mp) != len(sp): return None, f"pages {len(mp)}!={len(sp)}"
    out = []
    for m, s in zip(mp, sp):
        s = s.strip()
        mm = SPK_M.match(m); ms = SPK_S.match(s)
        if mm:
            if not ms: return None, "speaker_missing_in_ss"
            out.append("{#5}" + ms.group(1).strip() + ":" + BSN + "{#1}" + s[ms.end():])
        else:
            if "{#" in m: return None, "master_color_not_header"
            if ms and len(ms.group(1)) <= 6 and "(" not in ms.group(1): return None, "ss_speaker_extra"
            out.append(s)
    return BSP.join(out), "ok"


def squeezed(old: str, new: str) -> bool:
    """구 번역이 띄어쓰기를 지운 축약본인지: 한글 대비 공백 비율이 새 번역의 절반 미만."""
    def ratio(t):
        body = re.sub(r"\{[^}]*\}", "", t).replace(BSN, " ").replace(BSP, " ")
        h = sum(1 for c in body if 0xAC00 <= ord(c) <= 0xD7A3)
        sp = len(re.findall(r"(?<=\S) (?=\S)", body))
        return sp / h if h else 1.0
    return ratio(old) < 0.5 * ratio(new)


def main():
    ss = {}
    for r in csv.reader(io.open(SS, encoding="utf-8", newline=""), delimiter="\t"):
        try: ss[int(r[0], 16)] = r
        except ValueError: pass
    master = {r[0]: r for r in csv.reader(io.open(MASTER, encoding="utf-8", newline=""))}
    hdr = next(iter(master.values())); OI = [h.lstrip("\ufeff") for h in hdr].index("original")
    rows = list(csv.reader(io.open(MAP, encoding="utf-8", newline=""), delimiter="\t"))
    rep = [("id", "result", "old", "new")]; n = 0
    for r in rows[1:]:
        if r[2] != "OLD_FALLBACK": continue
        o = int(r[0][4:], 16); s = ss.get(o + 1) or ss.get(o)
        if not s or not s[-1].strip() or r[0] not in master: continue
        new, why = convert(master[r[0]][OI], s[-1])
        if new and not squeezed(r[5], new): why = "old_already_spaced"; new = None
        rep.append((r[0], why, r[5], new or ""))
        if new:
            r[2] = "SS_FULL"; r[5] = new; n += 1
    with io.open(MAP, "w", encoding="utf-8", newline="") as f: csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
    with io.open(REPORT, "w", encoding="utf-8", newline="") as f: csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rep)
    from collections import Counter
    print("replaced", n, Counter(x[1] for x in rep[1:]))


if __name__ == "__main__":
    main()
