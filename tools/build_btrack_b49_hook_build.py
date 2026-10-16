#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B49 — b49 + 표기 통일 2종 (2026-10-11 사용자 결정):
  · メロウズ = 메로우즈 (대사 멜로우즈 → 메로우즈 사본 포함 5레코드, 메뉴 9B 칸 2곳). 5B 이름 칸 40곳은 4글자가 안 들어가 오버라이드 「멜로즈」 유지
    (메·로만 1바이트 코드 → 메로우즈 6B). 원천 = xlsx·script_sheet·b3 맵·ziria_z8_text_entry_index·master 치환(백업 _backup/term_unify_2026-10-11_merrows/).
  · 掲げる = 「들어 올리다」 하나로: 흑마노 「내걸까요/내걸었다」→「들어 올리겠습니까/들어 올렸다」(보충 원천), 비문 3종 「・・・나를 이곳에 들어 올려라」,
    전승 『빛을 들어 올려라』, 불꽃 비문 「이곳에 들어 올려지리라」(b3_manual_fixes F·GLOBAL). 코크 왕 「높이 들어 올려다오」는 원래 같은 동사.
제자리 패치 = btrack_b49_full_menu_patches.json (b10 빌더 B10_OUT_TAG=b49 출력 + b45 의 card@ 19행; b45 대비 변경 = 0x10E3997·0x10E4997 두 곳).
빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b49_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b49.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b49.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b49.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b49_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b49_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b49_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
