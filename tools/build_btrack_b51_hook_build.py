#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B51 — b51 + 메뉴 이름 띄어쓰기 14종 (2026-10-11 사용자 결정: 「메뉴 글자를 늘릴 수 없다면 기본은 다 메뉴와 통일」).
  띄어쓰기만 다르던 이름(달의돌/달의 돌 등)을 메뉴 칸에 띄어 쓴 표기로 넣어 보니 14종 전부 들어감 → 메뉴를 대사 표기로 늘림(대사 변경 없음).
  원천 = ziria_z8_text_entry_index.csv 번역 열(달의 돌·신주 리레이트·에이놈 열매·강철 방패·엘븐 보우·회복 마법·강철 투구·황금 사자 방패·
  마법 지도·유리 가면·사슬 갑옷·환무검 시·아·신궁 프류·독살조 구이). 제자리 패치 = btrack_b51_full_menu_patches.json. 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b51_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b51.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b51.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b51.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b51_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b51_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b51_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
