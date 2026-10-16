#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B37 — b36 + **폰트 압축 + BIOS EX_GETFNT 패치** (256KB 카드 1단계, 2026-10-11).

- 12x12: 쓰는 글자(비한자 + 배정 한글 + 최종 텍스트에 실제로 나오는 코드)만 0x30000 부터 빈틈없이, 미사용 번호 → □.
- 16x16: 카드 미니게임 말풍선 문자 131자만(한글은 Galmuri14 **15px** 로 재생성 — 14px 렌더 획 빠짐 결함 수정), 그 외 요청은 12x12 경로.
- 옛 16x16 영역(0x10000-0x2BFFF)·옛 12x12 꼬리는 FF 로 비운다(직접 읽는 코드가 있으면 드러나도록). 대사 풀 배치는 b36 그대로(512KB).
- 빌드 끝에 미니 에뮬레이터로 원본 vs 패치 EX_GETFNT 출력 전수 비교(`font_compact.verify`).
출력: *_btrack_b37.bin/.cue + probes/SystemCard3_btrack_b37.pce
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b36_hook_build as b36
import build_btrack_b29_hook_build as b29
import build_btrack_b9_hook_build as b9
import font_compact as fc

OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b37.bin"
OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b37.cue"
OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b37.pce"
OUT_INFO = ROOT / "translation" / "btrack_b37_font_compact.json"
CREDIT_CODES = None   # (b58) 비주얼 크레딧 원문 SJIS 코드 — 드라이버가 설정(credits_original.credit_codes)


def main() -> None:
    b29.OUT_BIN, b29.OUT_CUE, b29.CARD_OUT = OUT_BIN, OUT_CUE, OUT_CARD
    b29.OUT_MANIFEST = ROOT / "translation" / "btrack_b37_hook_manifest.json"
    b36.main()
    card_b36 = OUT_CARD.read_bytes()
    extra = [r["encoded_hex"] for lba in b9.SCENES_B9 for r in b36._orig_payload(lba)]
    card, info = fc.build(card_b36, extra, CREDIT_CODES)
    stats = fc.verify(card_b36, card, info)
    assert stats["12_diff"] == 0 and not stats["err"] and stats["box"] == 6 and stats["invalid_code"] == (1, 1), stats
    OUT_CARD.write_bytes(card)
    OUT_INFO.write_text(json.dumps({"format": "B37-FONT-COMPACT", **{k: v for k, v in info.items() if k not in ("jmap", "c16")},
                                    "c16": [f"{c:04X}" for c in info["c16"]], "verify": stats}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": "B37_OK", "card": OUT_CARD.name, "verify": stats,
                      "keep12": info["keep12"], "n16": info["n16"], "newaddr": info["newaddr_bytes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
