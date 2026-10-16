#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B43 — b42 + 제자리 패치 재생성(B10_OUT_TAG=b43): 반칸 규칙에 「앞 글자가 1바이트 코드면 전각」 추가(「마랑루시에드의공 격」 게이트) + 미인덱스 전투 메시지 2건(전투 모듈 0x78AAC 「全ての魔法効果がかき消された！」→「모든　마법{~}효과{~}소멸!」, 0x78C09 カマイタチ→「{%s}　칼바람!」) + 미인덱스 행 반칸 정리. 패치 = translation/btrack_b43_full_menu_patches.json.
이하 b42 내용: b41 + 아실리에 공주 첫 쪽 「이 도시 사람이 아닌 게 뭘 어쩌라고！」→「이 도시 사람도 아니면서 무슨 참견이야！」(사용자 요청).
이하 b41 내용: b40 + 아실리에 공주 대사 중복 제거(iso:03AC2DB, 둘째 쪽 문장이 첫 쪽에도 들어감 — 씬 1826, 2026-10-11 게이트).
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
import build_btrack_b28_hook_build as b28

b37.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b43.bin"
b37.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b43.cue"
b37.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b43.pce"
b37.OUT_INFO = ROOT / "translation" / "btrack_b43_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b43_rearm_signatures.json"

import build_btrack_b35_hook_build as b35   # b35 가 import 때 b28.PATCHES 를 설정하므로 그 뒤에 덮어쓴다
b28.PATCHES = ROOT / "translation" / "btrack_b43_full_menu_patches.json"

if __name__ == "__main__":
    b38.main()
