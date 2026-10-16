#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B52 — b52 + 말줄임표 통일 (2026-10-11 사용자 요청): ASCII 「...」(마침표 연속)를 같은 개수의 「・」로.
  인코더가 ASCII 마침표를 전각 「．」(0x8144)로 올려 「．．．」로 찍히던 것 — 원문·나머지 대사 표기는 「・・・」(0x8145), 바이트 길이 같음.
  적용 = tools/apply_term_unify.py 의 DOTS 규칙(b3 맵·보충 원천·제자리 색인 — b3 는 apply_b3_manual_fixes 가 자동 재적용).
제자리 패치 = btrack_b52_full_menu_patches.json (b52 과 위치 동일, 0x8144→0x8145 만). 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b52_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b52.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b52.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b52.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b52_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b52_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b52_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
