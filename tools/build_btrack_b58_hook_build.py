#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B58 — b57 + 비주얼 씬 스태프 크레딧 원문 일본어 유지 (2026-10-12 제보: 컷신 뒤 제작진 정보가 □/엉뚱한 글자, 사용자 결정 = 원본 일본어 그대로).
  ① 디스크: 크레딧 구역(tools/credits_original.REGIONS — 성우 목록 0xC7B240, 스태프 롤 0x10E30F0·0x10E40F0)의 제자리 패치를 원본 바이트로
     (b57 까지: 이름을 한자 음독 직역 「矢尾一樹→시미일수」, 1바이트 코드·7E 채움 → 2바이트씩 읽는 크레딧 렌더러에서 □·막대).
  ② 카드: 크레딧 SJIS 코드 중 12x12 경로가 원본과 다른 글리프(한글 배정)를 주는 번호를 16x16 모드에서 원본 12x12 한자로(font_compact LISTK).
  제자리 패치 = btrack_b58_full_menu_patches.json(= b56 전체 패치 − 크레딧 구역). 트랙 확장 0(b57). 빌드 구성은 b46 과 동일."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
import build_btrack_b9_hook_build as b9
import credits_original as cr
from build_btrack_b7_hook_build import T2
b9.EXT_SECTORS = 0   # 트랙 확장 없음(오디오 트랙 절대 위치 = 원본, b57)

SRC_PATCHES = ROOT / "translation" / "btrack_b56_full_menu_patches.json"
PATCHES = ROOT / "translation" / "btrack_b58_full_menu_patches.json"
ORIG_ISO = (ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin").read_bytes()[T2:]

d = json.loads(SRC_PATCHES.read_text(encoding="utf-8"))
d["patches"], n_rev = cr.revert_patches(d["patches"], ORIG_ISO)
PATCHES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
b28.PATCHES = PATCHES
b37.CREDIT_CODES = cr.credit_codes(ORIG_ISO)

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b58.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b58.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b58.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b58_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b58_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b58_rearm_signatures.json"

if __name__ == "__main__":
    print(f"[b58] 크레딧 구역 되돌린 바이트 {n_rev}, 크레딧 코드 {len(b37.CREDIT_CODES)}", flush=True)
    m.main()
    iso = m.OUT_BIN.read_bytes()[T2:]
    for lo, hi in cr.REGIONS:
        assert iso[lo:hi] == ORIG_ISO[lo:hi], f"크레딧 구역 {lo:#x} 원본과 다름"
    print(json.dumps({"status": "B58_OK", "credit_regions_original": len(cr.REGIONS)}))
