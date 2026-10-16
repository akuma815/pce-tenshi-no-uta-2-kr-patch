#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B54 — b54 + 지명 표기 통일 (2026-10-11 사용자: 「표기 정리」).
  원칙: 지명 배너 칸에 대사 표기가 들어가면 배너를 늘림(봉옥의 탑·어둠의 신전·해신의 신전·오머의 탑·오키르의 동굴·키나리스 항구 등 20종),
  안 들어가면 대사를 배너 표기로(루시에드 마랑굴·교역 도시 에스트·해상성하 칼라·우라르투산·마르딘 바다동굴·적과 청의탑) + 고유명사 오기(카를라→칼라 등).
  원천 = 색인 location_names(전각 공백, 가운데 정렬 여백 재계산) + translation/respace/term_unify.py 지명 항목. 빌드 구성은 b46 과 동일."""
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

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b54.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b54.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b54.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b54_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b54_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b54_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
