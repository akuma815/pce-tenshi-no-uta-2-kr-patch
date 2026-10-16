#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B47 — b46(256KB 카드) + 씬 482 잘린 대사 3건 원문 전체 번역 (2026-10-11 게이트: 「Ⅱ 버튼」 누락 신고).
  · iso:010CABD 길 막는 사람 빠져나가기(とおせんぼ…Ⅱボタンを押すと…) — 첫 문장·방향키·Ⅱ 누락
  · iso:010D036 오토 배틀 해제(オートバトルは…戦闘中、Ⅱボタンを押し続けてね…) — 첫 쪽·「전투 중 Ⅱ」 누락
  · iso:011F01E 선택지 「次の目的のこと」 — 포인터 바이트 섞인 일본어 그대로 → 「다음 목적에 대해」
원인 = build_btrack_b4_field_encode.CORRECTED_TO_MASTER 의 master 가 원문 뒷부분만 담은 부분 문자열. 수정 = 같은 파일 CORRECTED_KO
(+ 인코더 Ⅱ → 0x8755 직결). 빌드 구성은 b46 과 동일(이름만 b47)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b47.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b47.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b47.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b47_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b47_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b47_rearm_signatures.json"

if __name__ == "__main__":
    m.main()
