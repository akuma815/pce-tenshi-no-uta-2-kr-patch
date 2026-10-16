#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B55 — b55 + 고유명사 표기 통일 5종 (2026-10-11 사용자: 「럭나캉 → 라그나캉, 아직 고유명사가 1개로 다 통일된 게 아닌가봐」).
  대사 원문 가타카나 고유명사 전수 감사(세션 proper_audit.py) → 럭나캉→라그나캉, 이슬란→이스란, 펜브로크→펨브로크, 에길→에기르, 어윈→아윈 (term_unify.py).
  디스크(메뉴) 변경 없음 — 제자리 패치는 b55 와 같음. 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b54_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b55.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b55.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b55.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b55_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b55_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b55_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
