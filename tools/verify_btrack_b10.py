#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B10 검증.

  1. **b9 검증기 전체를 b10 산출물로 재실행** (serve 시뮬 54씬·카드 diff·
     cue — 디스크 diff 는 메뉴 패치 구간을 허용 목록으로 주입, 카드 소스는
     full_v2 로 교체).
  2. 메뉴 패치 내용 검증: b10 bin 의 각 패치 구간 == new_hex, 패치 구간 밖
     b10 bin == b9 bin (전량 스캔).
  3. b10 카드 vs b9 카드 diff == b2x 추가 글리프 슬롯(15자)뿐.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b10_hook_build as b10
import verify_btrack_b9 as v9

FONT_BASE = 0x30000
GLYPH_BYTES = 18


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    doc = json.loads(b10.PATCHES.read_text(encoding="utf-8"))
    spans = sorted((b10.T2 + p["iso_off"],
                    b10.T2 + p["iso_off"] + len(p["old_hex"]) // 2)
                   for p in doc["patches"])
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        if e1 > s2:
            fail(f"패치 겹침 @{s1:07X}")

    # 1. b9 검증기 재실행 (b10 대상)
    v9.OUT_BIN = b10.OUT_BIN
    v9.OUT_CUE = b10.OUT_CUE
    v9.CARD_OUT = b10.CARD_OUT
    v9.CARD_SRC = b10.CARD_SRC_V2
    v9.EXTRA_ALLOWED = spans
    v9.main()

    # 2. 메뉴 패치 내용 + 패치 밖 b9 동일성
    out = b10.OUT_BIN.read_bytes()
    b9_bin = (ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b9.bin"
              ).read_bytes()
    if len(out) != len(b9_bin):
        fail("b10/b9 bin 크기 불일치")
    for p in doc["patches"]:
        off = b10.T2 + p["iso_off"]
        old = bytes.fromhex(p["old_hex"])
        new = bytes.fromhex(p["new_hex"])
        if out[off:off + len(new)] != new:
            fail(f"패치 내용 불일치 @iso {p['iso_off']:07X}")
        if b9_bin[off:off + len(old)] != old:
            fail(f"b9 원본 전제 불일치 @iso {p['iso_off']:07X}")
    pos = 0
    for s, e in spans:
        if out[pos:s] != b9_bin[pos:s]:
            fail(f"패치 밖 b10≠b9 ({pos:07X}..{s:07X})")
        pos = e
    if out[pos:] != b9_bin[pos:]:
        fail(f"패치 밖 b10≠b9 (꼬리)")

    # 3. 카드 diff = b2x 글리프 슬롯뿐
    assign = json.loads((ROOT / "translation/btrack_slot_assignment.json"
                         ).read_text(encoding="utf-8"))["assignment"]
    added = {ch: e for ch, e in assign.items() if e.get("b2x_added")}
    allowed = []
    for ch, e in added.items():
        lo = FONT_BASE + e["glyph_index"] * GLYPH_BYTES
        allowed.append((lo, lo + GLYPH_BYTES))
    c10 = b10.CARD_OUT.read_bytes()
    c9 = (ROOT / "probes/SystemCard3_btrack_b9.pce").read_bytes()
    if len(c10) != len(c9):
        fail("카드 크기 불일치")
    ndiff = 0
    for i in range(len(c10)):
        if c10[i] != c9[i]:
            ndiff += 1
            if not any(s <= i < e for s, e in allowed):
                fail(f"카드 diff 가 b2x 슬롯 밖 @{i:06X}")
    print(json.dumps({"status": "PASS",
                      "menu_patches": len(doc["patches"]),
                      "b2x_glyphs": len(added),
                      "card_diff_bytes_vs_b9": ndiff},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
