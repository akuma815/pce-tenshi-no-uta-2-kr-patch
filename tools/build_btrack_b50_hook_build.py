#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B50 — b50 + 이름 표기 통일 (2026-10-11 사용자 결정: 「이름이 2개씩 사용되면 혼돈스러워」).
  · メロウズ = 멜로즈, アレフ = 아레프(3B 칸 때문에 전부), 아이템·지명은 대사를 메뉴 표기와 똑같이(강철의 창 → 강철창, 발키리의 검 → 전처녀검 …).
  · 메뉴 쪽을 바꾼 고유명사(모든 칸에 들어가고 대사가 다수·표준): 사르가타나스·건틀릿·에우리카(의 꽃/씨)·선초 알님.
  · 통일표 = translation/respace/term_unify.py, 적용 = tools/apply_term_unify.py (b3 맵은 apply_b3_manual_fixes 가 자동 재적용).
제자리 패치 = btrack_b50_full_menu_patches.json (B10_OUT_TAG=b50 출력 + b45 card@ 19행). 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b50_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b50.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b50.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b50.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b50_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b50_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b50_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
