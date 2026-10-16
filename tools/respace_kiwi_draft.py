#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제자리(in-place) 메시지 번역의 띄어쓰기 초안: Kiwi.space + 게임 고유명사 사용자 사전. 제어 토큰·줄바꿈 단위로 쪼개 한글 구간만 처리.
결과 = translation/respace/inplace_kiwi_draft.json [[옛 텍스트, 새 텍스트], ...] (공백 외 변경 없음 검사 통과분만). 사람 검토 후 적용."""
import csv, io, json, re
from pathlib import Path
from kiwipiepy import Kiwi
csv.field_size_limit(10 ** 7)
ROOT = Path(__file__).resolve().parents[1]
IDX = ROOT / "translation" / "ziria_z8_text_entry_index.csv"
CAND = ROOT / "translation" / "respace" / "inplace_candidates.json"
OUT = ROOT / "translation" / "respace" / "inplace_kiwi_draft.json"
NAME_SUBS = {"location_names", "character_names", "monster_names", "weapon_names", "armour_names", "accessory_and_key_item_names",
             "item_names", "magic_names", "spell_names", "party_names"}
kiwi = Kiwi()
rows = list(csv.DictReader(io.open(IDX, encoding="utf-8-sig", newline="")))
names = set()
for r in rows:
    if r["category"] == "menu_data" or r["subcategory"] in NAME_SUBS:
        t = re.sub(r"\{[^}]*\}", " ", r["translation"] or "")
        for w in re.split(r"[\s\n]+", t):
            w = re.sub(r"[^가-힣]", "", w)
            if 2 <= len(w) <= 12: names.add(w)
EXTRA = "페이트 리아나 리아 시온 지아 란조 판 듀이 알레프 티아라 케알 라미암 라파엘 메로우즈 멜로우즈 바라바 사탄 루키페르 루키펠 사타나키아 살가타나스 아스타로트 아그네아 오리할콘 데몬게이트 아윈 에스트 라하사 칼라 카를라 켈즈 셀룸 우라르투산 엑스잔성 헬름즈테일 레이가르드 쿠린 마르딘 크리스탈탑 봉옥탑 성천문 천상계 지상계 지저계 마족 다크교 다크교단 다크신성기사단 기밀 이카로스 라그나캉 와이몬담 오킬 롱보우 엘븐 마장 마물 민첩 합체 마물들 마물을 마물이".split()
for w in names | set(EXTRA):
    try: kiwi.add_user_word(w, "NNP", 0.0)
    except Exception: pass
TOK = re.compile(r"(\{[^}]*\}|\\[npc]|[^\S\n]*[　]+[^\S\n]*)")


FIXES = [(r"다 지(?=$|[^가-힣])", "다지"), (r"다 잖아", "다잖아"), (r"잖 아", "잖아"), (r"다 는데", "다는데"), (r"해야해", "해야 해"),
         (r"가야해", "가야 해"), (r" 째(?= )", "째"), (r"마 물", "마물"), (r"합 체", "합체"), (r"민 첩", "민첩"), (r"(?<=[가-힣])한다 지", "한다지")]
JOSA = re.compile(r"^(에게|에서|으로|가|이|는|은|를|을|의|와|과|도|에|로)(?=[가-힣])")


def space(text):
    parts = TOK.split(text); out = []
    prev = ""
    for p in parts:
        if not p or TOK.fullmatch(p) or not re.search(r"[가-힣]", p):
            out.append(p)
            if p: prev = p
            continue
        lead = re.match(r"^[^가-힣]*", p).group(0); core = p[len(lead):]
        head = ""
        if not lead and re.fullmatch(r"\{%[sd]\}", prev or ""):
            m = JOSA.match(core)
            if m: head = m.group(1); core = core[len(head):]
        tail = re.search(r"[^가-힣]*$", core).group(0); body = core[:len(core) - len(tail)] if tail else core
        sp = kiwi.space(body, reset_whitespace=False).strip() if body else ""
        out.append(lead + head + (" " if head and sp else "") + sp + tail)
        prev = p
    new = "".join(out)
    for a, b in FIXES: new = re.sub(a, b, new)
    return new if new.replace(" ", "") == text.replace(" ", "") else None


def namelike(t):
    h = sum(1 for c in t if "가" <= c <= "힣")
    return h <= 7 and "{%" not in t and not re.search(r"[!?.…~다요]$", t.strip())


cand = json.loads(CAND.read_text(encoding="utf-8"))
res = []
for old, ids in cand:
    if namelike(old): continue
    new = space(old)
    if new and new != old: res.append([old, new])
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
print("names", len(names), "candidates", len(cand), "drafted", len(res))
