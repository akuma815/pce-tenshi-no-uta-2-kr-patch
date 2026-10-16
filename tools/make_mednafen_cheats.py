#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mednafen 용 치트 파일 생성 (2026-10-12): tools/cheat_tenshi2.lua(BizHawk)와 같은 4종을 Mednafen 치트 형식으로.
Mednafen 치트 = 「R(매 프레임 값 쓰기) A(켜짐) 길이 L 0 주소 값 이름」 + 다음 줄 조건(「1 L 주소 연산 값, …」 = 모두 참일 때만, 비면 항상).
PCE 주 RAM(BizHawk Main Memory 0x0000-0x1FFF) = Mednafen 주소 0x1F0000 + 오프셋. 값은 고정값만 가능(Lua 처럼 최대 HP 복사 불가) →
  무적·MP 무한 = 파티원이 있을 때(최대 HP/MP 의 lo 또는 hi ≠ 0) HP·MP 를 999 로 / 최고 레벨 = EXP 16,000,000 (다음 전투 뒤 Lv99) /
  전투 즉시 종료 = 전투 중(0x0005 = 0) 적 칸(전투 블록 4~11) HP 가 1 보다 크면 1 (lo > 1 → lo=1 / hi ≠ 0 → lo=1 그다음 hi=0, 0 인 적은 그대로).
게임 구분 = [디스크 TOC 해시] — b59·v0.3 = c62f2abf2f73a81b986dec23f3e07684 (0.1·0.2 = c7ac61b0cd9ece85dedf652370f81734).
사용: python -X utf8 tools/make_mednafen_cheats.py <출력 pce.cht> [게임 해시 …]
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
hashes = sys.argv[2:] or ["c62f2abf2f73a81b986dec23f3e07684"]
B = 0x1F0000
HP_LO, HP_HI, MAXHP_LO, MAXHP_HI = 0x1D7F, 0x1D83, 0x1D87, 0x1D8B
MP_LO, MP_HI, MAXMP_LO, MAXMP_HI = 0x1D8F, 0x1D93, 0x1D97, 0x1D9B
EXP0, EXP1, EXP2 = 0x1D67, 0x1D6B, 0x1D6F
BHP_LO, BHP_HI, BMAX_LO, BMAX_HI = 0x121C, 0x1228, 0x1234, 0x1240
BMP_LO, BMP_HI, BMMAX_LO, BMMAX_HI = 0x124C, 0x1258, 0x1264, 0x1270
MODE = 0x0005


def cheat(addr, val, name, conds=()):
    line = f"R A 1 L 0 {B + addr:08x} {val:02x} {name}"
    cond = ", ".join(f"1 L 0x{B + a:06X} {op} 0x{v:02X}" for a, op, v in conds)
    return [line, cond]


lines = []
for i in range(4):
    for present in ((MAXHP_LO + i, "!=", 0), (MAXHP_HI + i, "!=", 0)):          # 파티원 있음(최대 HP lo 또는 hi ≠ 0) — 두 변형으로 OR
        lines += cheat(HP_LO + i, 0xE7, f"[무적] {i + 1}번 HP 999 (lo)", [present])
        lines += cheat(HP_HI + i, 0x03, f"[무적] {i + 1}번 HP 999 (hi)", [present])
        lines += cheat(BHP_LO + i, 0xE7, f"[무적] {i + 1}번 전투 HP 999 (lo)", [(BMAX_LO + i, "!=", 0), (MODE, "==", 0)])
        lines += cheat(BHP_HI + i, 0x03, f"[무적] {i + 1}번 전투 HP 999 (hi)", [(BMAX_LO + i, "!=", 0), (MODE, "==", 0)])
    for present in ((MAXMP_LO + i, "!=", 0), (MAXMP_HI + i, "!=", 0)):
        lines += cheat(MP_LO + i, 0xE7, f"[MP무한] {i + 1}번 MP 999 (lo)", [present])
        lines += cheat(MP_HI + i, 0x03, f"[MP무한] {i + 1}번 MP 999 (hi)", [present])
        lines += cheat(BMP_LO + i, 0xE7, f"[MP무한] {i + 1}번 전투 MP 999 (lo)", [(BMMAX_LO + i, "!=", 0), (MODE, "==", 0)])
        lines += cheat(BMP_HI + i, 0x03, f"[MP무한] {i + 1}번 전투 MP 999 (hi)", [(BMMAX_LO + i, "!=", 0), (MODE, "==", 0)])
    p = (MAXHP_LO + i, "!=", 0)
    lines += cheat(EXP0 + i, 0x00, f"[최고레벨] {i + 1}번 EXP 16000000 (0)", [p])
    lines += cheat(EXP1 + i, 0x24, f"[최고레벨] {i + 1}번 EXP 16000000 (1)", [p])
    lines += cheat(EXP2 + i, 0xF4, f"[최고레벨] {i + 1}번 EXP 16000000 (2)", [p])
for e in range(4, 12):   # 적 8칸 — 같은 프레임 안에서 위에서부터 차례로 적용되므로 lo=1 을 hi=0 보다 먼저
    lines += cheat(BHP_LO + e, 0x01, f"[전투즉시종료] 적{e - 3} HP→1 (lo>1)", [(MODE, "==", 0), (BHP_LO + e, ">", 1)])
    lines += cheat(BHP_LO + e, 0x01, f"[전투즉시종료] 적{e - 3} HP→1 (hi≠0, lo)", [(MODE, "==", 0), (BHP_HI + e, "!=", 0)])
    lines += cheat(BHP_HI + e, 0x00, f"[전투즉시종료] 적{e - 3} HP→1 (hi≠0, hi)", [(MODE, "==", 0), (BHP_HI + e, "!=", 0)])
body = []
for h in hashes:
    body.append(f"[{h}] Tenshi no Uta II KR")
    body += lines
out.write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
print(out, "cheats per game:", len(lines) // 2)
