#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B12 — b10 + **armchk_v4 ($53 스트림 서브)**.

b10 과 디스크·카드 구성이 같고 **armchk 만 v4** 로 바뀐다. v3 는 `$53`≠0 을
무조건 거부해 메모·초상화 대사(고유 83종)가 일문으로 남았는데, v4 는 그
스트림의 포인터 쌍(zp $52/$53)으로 키를 산출하고 매치 시 그 쌍을 전진시킨다.

근거(2026-08-30 세이브스테이트 실측): 메모 화면 zp `$52=31 $53=C0` →
소스키 `0x10031` = ISO `0xA1031`('ダーク教のこと') 로 **기본 스트림과 키
공간이 동일**. 디스패처 $4284 의 우선순위($55 > $53 > $2E69 > 기본)도
armchk 검사 순서에 반영했다.

⚠ 이 변경은 **정상 동작 중인 대사 서브 전체**에 영향을 준다. b10 을 남겨
두고 별도 산출물로 빌드하니, 회귀가 보이면 b10 으로 즉시 되돌릴 것.

출력: *_btrack_b12.bin/.cue + probes/SystemCard3_btrack_b12.pce
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b9_hook_build as b9

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b12"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b12.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b12_hook_manifest.json"
CARD_SRC_V2 = ROOT / "probes" / "SystemCard3_btrack_full_v2.pce"
PATCHES = ROOT / "translation" / "btrack_b10_menu_patches.json"
T2 = b9.T2


def main() -> None:
    b9.OUT_BIN = OUT_BIN
    b9.OUT_CUE = OUT_CUE
    b9.CARD_OUT = CARD_OUT
    b9.OUT_MANIFEST = ROOT / "translation" / "btrack_b12_b9stage_manifest.json"
    b9.CARD_SRC = CARD_SRC_V2
    b9.ARMCHK_BUILDER = b9.asm_armchk_v4      # $53 스트림 키/전진
    b9.HOOK_DISPATCH = True                   # 훅을 $4036 → $4284 로
    b9.main()

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
        "format": "BTRACK-B12-HOOK-BUILD",
        "runtime_status": "PENDING",
        "base": "b10 구성 + armchk_v4 + 디스패처($4284) 훅",
        "armchk": {"builder": "asm_armchk_v4",
                   "bytes": len(b9.asm_armchk_v4()),
                   "scratch": {"PTRL": hex(b9.PTRL_V4),
                               "PTRH": hex(b9.PTRH_V4),
                               "STREAM": hex(b9.STREAM_V4)}},
        "menu_stage": {"patches": len(doc["patches"]), "patched_bytes": total},
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK", "bin": OUT_BIN.name,
                      "card": CARD_OUT.name, "menu_patches": len(doc["patches"]),
                      "armchk_bytes": len(b9.asm_armchk_v4())},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
