#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B41 — b40 + 아실리에 공주 대사 중복 제거(iso:03AC2DB, 둘째 쪽 문장이 첫 쪽에도 들어감 — 씬 1826, 2026-10-11 게이트).
이하 b40 내용: b39 + 무기·도구점 「바다의 집」 퇴장 인사 「どうもです」 「안녕하세요」→「감사합니다」(씬 1826, 사본 iso:03AC68F·03AC6EE, 2026-10-11 게이트).
이하 b39 내용: b38 + 대사 수정 2건(씬 1442, 2026-10-11 게이트): 「아크로바틱 보여줄래？」→「볼래？」(見てくれる, 사본 3개),
「여성 하면 바다・・・」→「여성이라고 하면 역시 바다지・・・」·「북쪽으로 간 섬」→「북쪽으로 가면 나오는 섬」(女性といえば海).
수정 원천 = translation/respace/b3_manual_fixes.py → apply_b3_manual_fixes.py → build_btrack_b7_scene_encode.py 1442. 빌드 구성은 b38 과 동일(이름만 b41)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37

b37.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b41.bin"
b37.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b41.cue"
b37.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b41.pce"
b37.OUT_INFO = ROOT / "translation" / "btrack_b41_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b41_rearm_signatures.json"

if __name__ == "__main__":
    b38.main()
