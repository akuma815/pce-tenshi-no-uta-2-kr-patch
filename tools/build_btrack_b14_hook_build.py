#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B14 — b13 + 보류 클래스(asset_confirmed_short_event_text) 편입: 인라인 행은 b9 보충 카드 서브, 이름 테이블 행은 b10 제자리(b14 패치). 원 b13 설명:
b10 + **armchk_v5 (`$2E69` 스트림 = 초상화 대사 카드 서브)**.

근거 (2026-10-09 PCEHawk 실측, `tools/trace_b13_fetch_loop.lua` /
`trace_b13_stream_paths.lua`, `translation/b13_fetch_trace/`):

- 초상화 대사는 `JSR $4036 → $4284` 를 **정상적으로 경유**한다. 디스패처의
  ③ 경로(`$2E69`≠0): `MPR6 = $22D0 + $2E69` 로 스왑 후 `LDA ($4B)`.
  실측 `$22D0=68, $2E69=0E → 뱅크 $76`, 포인터 `$4B/$4C = D9BF`,
  물리 `0ED9BF` = 씬 2882 상대 `0x1D9BF` (b9 레코드 키 `0x1D98C`, 83B,
  번역 있음).
- armchk_v3 는 진입 직후 `LDA $2E69 / BNE pass` 로 이 경로를 **무조건 거부**
  했다. "어느 훅도 안 탄다"(HANDOFF §6 구판)는 오진 — 훅은 타지만 armchk 가
  스크래치를 쓰기 전에 빠져나갔을 뿐이다. v4 (b11/b12) 도 같은 거부를 유지했다.

v5 = v3 + ③ 경로 지원:
  `$2E69`≠0 이면 kb = `$22D0 + $2E69 − $68` (뱅크가 곧 키 상위), `$4C` 는
  MPR6 창(`$C0-$DF`) 안이어야 한다. 키 하위(`$4C&$1F`,`$4B`)·매치·전진·서브는
  v3 와 동일 — ③ 경로도 같은 `$4B/$4C` 포인터를 쓰기 때문이다.
  `$53` 스트림(메모)은 v3 대로 계속 거부한다 (경로 ② 는 엔진 뱅크 `$84` 를
  읽는 경우가 실측돼 씬 키 공간과 다르다 — 별도 조사).

출력: *_btrack_b14.bin/.cue + probes/SystemCard3_btrack_b14.pce
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b9_hook_build as b9
Asm = b9.Asm  # b7 계열 Asm (jsr·resolve() 지원)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b14"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b14.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b14_hook_manifest.json"
CARD_SRC_V2 = ROOT / "probes" / "SystemCard3_btrack_full_v3.pce"
PATCHES = ROOT / "translation" / "btrack_b14_menu_patches.json"
T2 = b9.T2


def asm_armchk_v5() -> bytes:
    a = Asm(b9.ARMCHK_EXEC)
    a.emit(0xDA, 0x5A)                                   # PHX PHY
    a.emit(0xA5, 0x53)                                   # LDA $53
    a.branch(0xD0, "p0")                                 # $53 스트림 → 거부 (v3 동일)
    a.emit(0xAD, 0x69, 0x2E)                             # LDA $2E69
    a.branch(0xF0, "dflt")                               # 0 → 기본 경로
    # --- ③ 경로: kb = $22D0 + $2E69 - $68 ---
    a.emit(0x18, 0x6D, 0xD0, 0x22)                       # CLC ADC $22D0
    a.emit(0x38, 0xE9, 0x68)                             # SEC SBC #$68
    a.emit(0xC9, 0x18)                                   # CMP #24
    a.branch(0xB0, "p0")
    a.emit(0xAA)                                         # TAX (kb)
    a.emit(0xA5, 0x4C, 0xC9, 0xC0)                       # LDA $4C CMP #$C0
    a.branch(0x90, "p0")
    a.emit(0xC9, 0xE0)                                   # CMP #$E0
    a.branch(0xB0, "p0")
    a.branch(0x80, "common")
    # --- 기본 경로 (v3 그대로) ---
    a.label("dflt")
    a.emit(0xA5, 0x4C, 0xC9, 0x80)
    a.branch(0x90, "p0")
    a.emit(0xC9, 0xE0)
    a.branch(0xB0, "p0")
    a.emit(0x4A, 0x4A, 0x4A, 0x4A, 0x4A)
    a.emit(0x18, 0x69, 0x08)
    a.emit(0x6D, 0xD0, 0x22)
    a.emit(0x38, 0xE9, 0x68)
    a.emit(0xC9, 0x18)
    a.branch(0xB0, "p0")
    a.emit(0xAA)                                         # TAX (kb)
    a.label("common")
    a.emit(0x64, 0x00)                                   # STZ $00
    a.emit(0xAD, b9.IBASE & 0xFF, b9.IBASE >> 8)         # LDA IBASE
    a.emit(0x85, 0x01)                                   # STA $01
    a.emit(0xA0, 0x00)                                   # LDY #0
    a.emit(0xB1, 0x00, 0xC9, b9.INDEX_MAGIC[0])
    a.branch(0xD0, "p0")
    a.emit(0xC8, 0xB1, 0x00, 0xC9, b9.INDEX_MAGIC[1])
    a.branch(0xD0, "p0")
    a.branch(0x80, "cont")
    a.label("p0")
    a.jmp("pass")
    a.label("cont")
    a.emit(0xA5, 0x4C, 0x29, 0x1F)
    a.emit(0x8D, b9.SCRATCH_KH_V3 & 0xFF, b9.SCRATCH_KH_V3 >> 8)
    a.emit(0x8A, 0x0A)                                   # TXA ASL
    a.emit(0x18, 0x69, 0x02)                             # CLC ADC #2
    a.emit(0xA8)                                         # TAY
    a.emit(0xB1, 0x00, 0x48)                             # LDA ($00),Y PHA
    a.emit(0xC8, 0xB1, 0x00)                             # INY LDA ($00),Y
    a.emit(0x85, 0x01)                                   # STA $01
    a.emit(0x68, 0x85, 0x00)                             # PLA STA $00
    a.label("loop")
    a.emit(0xA0, 0x00)
    a.emit(0xB1, 0x00)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "pass")
    a.emit(0xCD, b9.SCRATCH_KH_V3 & 0xFF, b9.SCRATCH_KH_V3 >> 8)
    a.branch(0xD0, "next")
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0xC5, 0x4B)
    a.branch(0xF0, "match")
    a.label("next")
    a.emit(0x18, 0xA5, 0x00, 0x69, 0x07, 0x85, 0x00)
    a.branch(0x90, "loop")
    a.emit(0xE6, 0x01)
    a.branch(0x80, "loop")
    a.label("match")
    a.emit(0xA0, 0x02)
    a.emit(0xB1, 0x00, 0x8D, b9.TBANK & 0xFF, b9.TBANK >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, b9.CURL & 0xFF, b9.CURL >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, b9.CURH & 0xFF, b9.CURH >> 8)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x65, 0x4C, 0x85, 0x4C)
    a.emit(0xA9, 0x01, 0x8D, b9.FLAG & 0xFF, b9.FLAG >> 8)
    a.emit(0x7A, 0xFA)
    a.emit(0x18, 0x60)
    a.label("pass")
    a.emit(0x7A, 0xFA)
    a.emit(0x38, 0x60)
    return a.resolve({})


def main() -> None:
    v3 = b9.asm_armchk_v3()
    v5 = asm_armchk_v5()
    # 자기검증: v5 의 공통부(매직 검사 이후)는 v3 와 바이트 동일해야 한다.
    tail3 = v3[v3.index(bytes((0x64, 0x00, 0xAD))):]
    tail5 = v5[v5.index(bytes((0x64, 0x00, 0xAD))):]
    # 분기 오프셋은 상대값이라 동일, 절대 주소(JMP pass)는 위치에 따라 다르다 → JMP 피연산자만 제외하고 비교
    def strip_jmp(b: bytes) -> bytes:
        i = b.index(0x4C)
        return b[:i + 1] + b[i + 3:]
    assert strip_jmp(tail3) == strip_jmp(tail5), "v5 공통부가 v3 와 다르다"

    b9.OUT_BIN = OUT_BIN
    b9.OUT_CUE = OUT_CUE
    b9.CARD_OUT = CARD_OUT
    b9.OUT_MANIFEST = ROOT / "translation" / "btrack_b14_b9stage_manifest.json"
    b9.CARD_SRC = CARD_SRC_V2
    b9.ARMCHK_BUILDER = asm_armchk_v5            # ← b13 의 유일한 차이
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
        "format": "BTRACK-B14-HOOK-BUILD",
        "runtime_status": "PENDING",
        "base": "b10 구성 + armchk_v5 ($2E69 스트림 = 초상화 대사)",
        "armchk": {"builder": "asm_armchk_v5", "bytes": len(v5), "v3_bytes": len(v3),
                   "hex": v5.hex()},
        "menu_stage": {"patches": len(doc["patches"]), "patched_bytes": total},
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK", "bin": OUT_BIN.name,
                      "card": CARD_OUT.name, "menu_patches": len(doc["patches"]),
                      "armchk_bytes": len(v5)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
