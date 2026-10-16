#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B48 — b47 + 씬 3746 여신상 제단 문구 (2026-10-11 게이트):
  · iso:076BD2B 화자 앞 「#5」가 글자로 찍힘(「{#5}#5듀이」 — 번역 데이터 오류) → 「{#5}듀이」
  · 비문 3종(076B9FB·076BD2B·076C067) ASCII ' " ... → 「」·・・・ (게임에서 ’…’ ”…” ．．． 로 찍혔다)
  · 흑마노를내걸었다 → 흑마노를 내걸었다 (보충 원천 b9_gap_supplement_source.tsv, 사본 3)
  · iso:03AC586(씬 1826) "잘 부탁해" → 「잘 부탁해」
  · 화자명 뒤 콜론 없는 6건(076A151 페이트·055BB47 아니스；·085AC87 럭나캉 데몬·085AD90 라미암·085B154 로브의 남자·0A9A706 알레프) → 「이름：」 —
    인코더가 화자 줄로 못 알아보고 이름과 대사를 한 줄로 합쳤다(씬 2690·3746·4226·5378).
수정 원천 = b3_manual_fixes.py F + b9_gap_supplement_source.tsv → apply_b3_manual_fixes → build_btrack_b9_gap_supplement → build_btrack_b7_scene_encode 3746 1826 2690 4226 5378.
빌드 구성은 b46 과 동일(이름만 b48)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b48.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b48.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b48.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b48_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b48_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b48_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
