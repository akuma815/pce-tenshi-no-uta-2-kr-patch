#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B56 — b56 + 미번역 전투 메시지 1건 (2026-10-11 게이트: 라그나캉 전 「□□は□をきった」).
  디스크 0x8A857 「攻撃は空をきった」 → 「빗나갔다！」(10/11B) — b10_unindexed_battle.tsv. 전투 메시지 영역(0x89000-0x8AFFF, 0x78000-0x79FFF) 원문 잔존 전수 = 이 1건.
  제자리 패치 = btrack_b56_full_menu_patches.json. 카드는 b56 와 같음. 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b56_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b56.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b56.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b56.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b56_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b56_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b56_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
