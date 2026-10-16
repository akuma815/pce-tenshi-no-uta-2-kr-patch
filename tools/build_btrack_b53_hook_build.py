#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B53 — b53 + 스크립트 사이 문자열의 채움 바이트 수정 (2026-10-11 사용자 게이트: b51 퀵세이브 → 계단 → 마을 진입 검은 화면).
  원인: 마을 지명 배너(「12 91 CC 02 {~}{~}双子の街ストーム 00 09 1B …」)의 번역이 짧아 남은 칸을 00 으로 채움 → 엔진이 첫 00 다음 바이트부터
  스크립트를 이어 읽다 채움 00 을 명령으로 해석 → 마을 적재 스크립트가 끊김(0.1 부터의 결함). 사용자 퀵세이브 + RAM 포크(00→7E)로 원인 확정.
  수정 = 제자리 빌더: 앞 바이트가 00 이 아닌 단독 레코드는 남은 칸을 반각 공백 7E 로 채우고 끝 00 은 원래 위치(몬스터·보스 이름표 제외) — 298 레코드
  (배너·「문이 열렸다!」·아이템 획득·괭이·상자 메시지·크레딧 등). 제자리 패치 = btrack_b53_full_menu_patches.json. 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
b28.PATCHES = ROOT / "translation" / "btrack_b53_full_menu_patches.json"   # b45 import 가 설정한 값을 덮어씀

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b53.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b53.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b53.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b53_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b53_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b53_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
