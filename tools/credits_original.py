#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비주얼 씬 스태프 크레딧 = 원문 일본어 유지 (2026-10-12 사용자 결정 — 제보: 컷신 뒤 제작진 정보가 □/엉뚱한 글자).

크레딧은 비주얼 모듈의 문자열 렌더러가 **2바이트씩** 읽어 EX_GETFNT(16x16 모드, $2A82)로 그린다(1바이트 코드 처리 없음).
b56 까지는 제자리 빌더가 이 문자열들을 번역(이름은 한자 음독 직역, 1바이트 코드·7E 채움 포함)해 깨졌다.
→ ① 디스크: 아래 구역의 제자리 패치를 원본 바이트로 되돌린다. ② 카드: 이 구역에 나오는 SJIS 코드를 font_compact 에 넘겨
   16x16 모드에서 원본 12x12 한자 글리프로 그리게 한다(font_compact.build(credit_codes=…)).
"""
from __future__ import annotations

import re

# 원본 데이터 트랙(T2 기준 바이트 오프셋) 크레딧 구역
REGIONS = [
    (0xC7B240, 0xC7B340),     # 성우 목록(짧은 판, 비주얼 모듈 0xC76881)
    (0x10E30F0, 0x10E3D80),   # 스태프 롤(비주얼 모듈 0x10DE881)
    (0x10E40F0, 0x10E4D80),   # 같은 스태프 롤 사본
]


# (b59) 제자리 색인 오탐 — 바이너리(그래픽 데이터) 안의 우연한 바이트를 텍스트로 보고 번역한 행. 원본으로 되돌린다.
#   0xC890D1 「7E C7 B4 00」 = 몬스터명 「ヌエ」(반각 ﾇｴ) 로 오인 → 첫 컷신(첫 탑 여주인공 뒤) 그래픽 블록이라 화면 전체가 깨짐
#     (사용자 퀵세이브 3: Super System Card RAM 0x60D1 에 바뀐 바이트 「7E D9 BC 00」 그대로 적재 확인).
#   0x10BA4F5 「D2 D3 00」 = 「メモ」(반각 ﾒﾓ) 로 오인 — 다른 비주얼 그래픽 블록.
#   찾는 법: 바뀐 짧은(≤4B)·반각 가나 행 중 ±32B 안에 다른 색인 행이 없는 것(tools/audit_binary_patches.py 계열, 2026-10-12 전수 3건 — 나머지 1건 状態 는 실제 텍스트).
FALSE_POSITIVES = [(0xC890D1, 0xC890D5), (0x10BA4F5, 0x10BA4F8)]
REVERT = REGIONS + FALSE_POSITIVES

# (b59) 명령 「01 <모드> <x> <y> 문자열 00」 의 모드 바이트(& 1 → $2A82: 0 = 16x16, 1 = 12x12, 크레딧 모듈 0x10E3883 실측).
# 12x12 모드 문자열의 한자가 한글 배정과 겹치면(督 → 뇨) 12x12 로는 원본 한자를 못 그리므로 그 문자열만 16x16 모드(LISTK)로 바꾼다.
MODE16 = ["作画監督"]


def mode_patches(orig_iso: bytes) -> list[dict]:
    out = []
    for s in MODE16:
        enc = s.encode("cp932") + b"\x00"
        for lo, hi in REGIONS:
            j = lo
            while True:
                j = orig_iso.find(enc, j, hi)
                if j < 0:
                    break
                off = j - 4
                assert orig_iso[off] == 0x01 and orig_iso[off + 1] == 0x01, f"{s} @{j:#x}: 01 01 명령 아님"
                out.append({"iso_off": off + 1, "old_hex": "01", "new_hex": "00", "id": f"credit_mode16@{off + 1:07X}", "mode": "bytes"})
                j += 1
    assert out, "MODE16 문자열 없음"
    return out


def credit_codes(orig_iso: bytes) -> set[int]:
    """구역 안 0 으로 끝나는 SJIS 2바이트 문자열의 코드 전부."""
    out = set()
    for lo, hi in REGIONS:
        for m in re.finditer(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\xfc])+(?=\x00)", orig_iso[lo:hi]):
            s = m.group(0)
            out |= {s[2 * k] << 8 | s[2 * k + 1] for k in range(len(s) // 2)}
    return out


def revert_patches(patches: list[dict], orig_iso: bytes) -> tuple[list[dict], int]:
    """제자리 패치 중 크레딧 구역에 걸친 바이트를 원본으로. 결과가 원본과 같아진 패치는 뺀다. (패치 목록, 되돌린 바이트 수)."""
    out, n = [], 0
    for p in patches:
        off = p["iso_off"]; new = bytearray(bytes.fromhex(p["new_hex"])); old = bytes.fromhex(p["old_hex"])
        for lo, hi in REVERT:
            a, b = max(lo, off), min(hi, off + len(new))
            for i in range(a, b):
                if new[i - off] != orig_iso[i]:
                    new[i - off] = orig_iso[i]; n += 1
        if bytes(new) == old:
            continue
        q = dict(p); q["new_hex"] = bytes(new).hex().upper()
        out.append(q)
    return out, n
