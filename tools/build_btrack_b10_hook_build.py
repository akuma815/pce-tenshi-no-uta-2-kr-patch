#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B10 — b9(전 씬 대사 카드 상주) + 메뉴/전투/UI/이름 테이블 한글화.

구성 = b9 빌드 전체 + `btrack_b10_menu_patches.json` 의 제자리/재패킹 패치:
  - 카드 베이스 = SystemCard3_btrack_full_v2.pce (b2x 로 15자 추가 배정
    — 기존 1,053자 배정 불변, 여유 슬롯 사용).
  - 디스크 = b9 디스크 + 메뉴 패치(문자열·포인터 테이블 재작성).
    메뉴 패치 대상은 전부 b9 무접촉 영역(씬/공유 모듈의 문자열 바이트).
b9 모듈을 임포트해 출력 경로·카드 소스만 b10 으로 바꿔 그대로 실행한다
(로직 복제 금지 — b9 가 단일 소유).

출력: *_btrack_b10.bin/.cue + probes/SystemCard3_btrack_b10.pce (768KB)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b9_hook_build as b9

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b10"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b10.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b10_hook_manifest.json"
CARD_SRC_V2 = ROOT / "probes" / "SystemCard3_btrack_full_v2.pce"
PATCHES = ROOT / "translation" / "btrack_b10_menu_patches.json"
T2 = b9.T2


def main() -> None:
    # b9 빌드를 b10 이름·v2 카드 베이스로 실행
    b9.OUT_BIN = OUT_BIN
    b9.OUT_CUE = OUT_CUE
    b9.CARD_OUT = CARD_OUT
    b9.OUT_MANIFEST = ROOT / "translation" / "btrack_b10_b9stage_manifest.json"
    b9.CARD_SRC = CARD_SRC_V2
    b9.main()

    # 메뉴 패치 적용 (전 패치: 원본 바이트 전제조건 검증 후 치환)
    doc = json.loads(PATCHES.read_text(encoding="utf-8"))
    out = bytearray(OUT_BIN.read_bytes())
    total = 0
    for p in doc["patches"]:
        off = T2 + p["iso_off"]
        old = bytes.fromhex(p["old_hex"])
        new = bytes.fromhex(p["new_hex"])
        assert len(old) == len(new)
        if bytes(out[off:off + len(old)]) != old:
            raise ValueError(f"패치 전제 불일치 @iso {p['iso_off']:07X}")
        out[off:off + len(new)] = new
        total += len(new)
    OUT_BIN.write_bytes(bytes(out))

    manifest = {
        "format": "BTRACK-B10-HOOK-BUILD",
        "runtime_status": "PENDING",
        "base": "b9 (build_btrack_b9_hook_build, card base = full_v2)",
        "menu_stage": {"patches": len(doc["patches"]),
                       "patched_bytes": total,
                       "stats": doc["stats"] | {"window_report": "생략"},
                       "review": doc["review"]},
        "b9_stage_manifest": "btrack_b10_b9stage_manifest.json",
    }
    manifest["menu_stage"]["stats"].pop("window_report", None)
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK",
                      "menu_patches": len(doc["patches"]),
                      "menu_bytes": total,
                      "bin": OUT_BIN.name, "card": CARD_OUT.name},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
