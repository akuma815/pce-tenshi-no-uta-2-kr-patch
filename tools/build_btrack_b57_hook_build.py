#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B57 — b56 + 리아나 기억 회복 장면 3곳 (2026-10-11 게이트, iso:05BA57B, b3_manual_fixes.py).
  魔将がこの世界に持ち込んだ → 「마장들이 이 세계에 들여온」, この次元から → 「이 차원에서」(「이차원」 = 異次元 오독), 使命の遂行はどうした → 「사명 수행은 어떻게 됐지？」.
  제자리 패치 = b56 과 같음(btrack_b56_full_menu_patches.json). 빌드 구성은 b46 과 동일.
  ⚠ 데이터 트랙 끝 확장(+1024섹터, b8 부터) 제거 — 비주얼 씬이 CD-DA 를 트랙 번호가 아닌 절대 위치로 찾아(트랙 25 중간 등) 확장만큼(13.65초) 앞 부분을
  재생 → 영상·음성 싱크 어긋남(2026-10-11 사용자 게이트, 퀵세이브 1 위쪽 이벤트). 확장 구간은 b56 에서 전부 00(미사용) → 0 으로 두면 오디오 트랙 위치 = 원본."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
import build_btrack_b9_hook_build as b9
b9.EXT_SECTORS = 0   # 트랙 확장 없음(오디오 트랙 절대 위치 = 원본)
b28.PATCHES = ROOT / "translation" / "btrack_b56_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b57.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b57.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b57.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b57_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b57_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b57_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
