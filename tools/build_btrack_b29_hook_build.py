#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B29 — b28 + 카드 미니게임 UI 그래픽(BG 타일) 한글화.

카드 미니게임의 UI 문구(상대 차례/득점 계산 표/역 이름/규칙/경품 교환 목록 등)는 텍스트가 아니라
사전 렌더된 4bpp 8x8 BG 타일이다. 타일 시트는 ISO 0xBE3000 + (VRAM 타일 번호 × 32) 에 선형 적재되며
(0xBEB000~0xBF3000 = 타일 0x400~0x7FF), BAT 는 모듈이 RAM 의 lo/hi 평면(TurboCD RAM)에서 조립한다.
→ `tools/cardgame_tiles_kr.py` 가 PCEHawk VRAM 덤프(translation/cardgame/vram/s3~s7) 의 셀→타일 대응으로
   한글 렌더를 타일 단위로 제자리 교체한 패치 목록(translation/btrack_b29_cardgame_tiles.json)을 만들고,
   본 드라이버가 b28 빌드 위에 그 패치를 디스크에 적용한다. 카드(syscard)는 b28 과 동일 내용.
교훈: 타일 시트에는 **내용이 같은 중복 타일**이 있어 내용 기반 매칭을 쓰면 가짜 공유가 생긴다 → 선형 주소 매핑.
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b28_hook_build as b28

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b29"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b29.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b29_hook_manifest.json"
TILES = ROOT / "translation" / "btrack_b29_cardgame_tiles.json"
T2 = b28.T2


def main() -> None:
    b28.OUT_BIN, b28.OUT_CUE, b28.CARD_OUT = OUT_BIN, OUT_CUE, CARD_OUT
    b28.OUT_MANIFEST = ROOT / "translation" / "btrack_b29_b28stage_manifest.json"
    b28.main()
    doc = json.loads(TILES.read_text(encoding="utf-8"))
    assert doc["format"] == "CARDGAME-TILES-B29" and not doc["conflicts"], "타일 패치에 충돌이 남아 있음"
    out = bytearray(OUT_BIN.read_bytes())
    for p in doc["patches"]:
        off = T2 + p["iso_off"]
        old = bytes.fromhex(p["old_hex"]); new = bytes.fromhex(p["new_hex"])
        assert len(old) == len(new) == 32
        if bytes(out[off:off + 32]) != old:
            raise ValueError(f"타일 원본 불일치 @iso {p['iso_off']:07X}")
        out[off:off + 32] = new
    OUT_BIN.write_bytes(bytes(out))
    # .cue 의 FILE 이름을 b29 로
    cue = OUT_CUE.read_text(encoding="utf-8")
    assert OUT_BIN.name in cue, "cue 가 b29 bin 을 가리키지 않음"
    m = json.loads(b28.OUT_MANIFEST.read_text(encoding="utf-8"))
    m.update({"format": "BTRACK-B29-HOOK-BUILD", "cardgame_tiles": {"patches": len(doc["patches"]), "source": TILES.name}})
    OUT_MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK", "bin": OUT_BIN.name, "card": CARD_OUT.name, "cardgame_tiles": len(doc["patches"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
