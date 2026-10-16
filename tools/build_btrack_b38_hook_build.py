#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B38 — b37 + **카드 게임 종료 후 재무장을 전 씬으로 일반화** (2026-10-11).

증상(사용자 b37 게이트): 카드 게임을 마치고 나오면 주점 대사가 일본어. b30 재무장 루틴은 씬 770(에스트 도박사) 서명
($75:$120C 16B)만 검사했는데, 카드 게임은 다른 마을에서도 열린다 — 사용자 퀵세이브 RAM 덤프 = **씬 1442 상주**(레코드 272개 중 266개가
키 위치 원문과 일치). → 서명 불일치로 PRESENT=0 유지 → 원문 서브.
수정: 재무장 루틴 v2(카드 뱅크 $1F 머리 = MPR5 창 $A000, b37 폰트 압축으로 빈 자리)가 54씬 각각의 서명(그 씬에만 있는 대사 원문 6바이트 @ 그 레코드의 키 위치)을
Super System Card RAM 에서 확인 → 맞는 씬의 테이블 행(같은 뱅크 $1F 의 씬 테이블, $B054 + i*44 + 2)을 SCRATCH 로 복사, PRESENT=1, FLAG=0.
엔진 스텁 $C89F: MPR5 = $3F → $1F, JSR $AF00 → $A000. 씬 테이블이 같은 뱅크($B054)라 MPR3 조작 불필요.
출력: *_btrack_b38.bin/.cue + probes/SystemCard3_btrack_b38.pce
"""
from __future__ import annotations

import collections
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b37_hook_build as b37
import build_btrack_b36_hook_build as b36
import build_btrack_b9_hook_build as b9
import build_btrack_b7_hook_build as b7
from build_btrack_b7_hook_build import Asm, FLAG, PRESENT, SCRATCH, CARD_TABLE_OFF, ENTRY_LEN

b37.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b38.bin"
b37.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b38.cue"
b37.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b38.pce"
b37.OUT_INFO = ROOT / "translation" / "btrack_b38_font_compact.json"
OUT_SIG = ROOT / "translation" / "btrack_b38_rearm_signatures.json"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"

REARM_BANK = 0x1F                        # b37 폰트 압축으로 빈 옛 12x12 꼬리(0x3E000-0x3F053) — 씬 테이블과 같은 뱅크
REARM2_OFF = 0x0000
REARM2 = 0xA000 + REARM2_OFF             # 스텁이 MPR5 = $1F 로 매핑
REARM2_END = CARD_TABLE_OFF - REARM_BANK * 0x2000
SIG_N = 6
TABLE_WIN = 0xA000 + (CARD_TABLE_OFF - REARM_BANK * 0x2000)   # 같은 창에서 씬 테이블 ($B054)


def pick_signatures():
    """씬마다 (키, 원문 앞 SIG_N 바이트) — 다른 씬의 같은 키에 같은 원문이 없는 레코드만, 뱅크 경계 안."""
    rows = list(csv.reader(io.open(MASTER, encoding="utf-8", newline="")))
    h = {x.lstrip("﻿"): i for i, x in enumerate(rows[0])}
    raw = {r[h["id"]]: bytes.fromhex(r[h["raw_hex"]]) for r in rows[1:] if r[h["raw_hex"]]}
    per = {}
    seen = collections.Counter()
    for lba in b9.SCENES_B9:
        lst = []
        for r in b36._orig_payload(lba):
            rb = raw.get(r["master_id"]) or raw.get(r["id"])
            k = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
            if rb is None or len(rb) < SIG_N or (k & 0x1FFF) + SIG_N > 0x2000 or len(set(rb[:SIG_N])) < 3:
                continue
            lst.append((k, rb[:SIG_N]))
        per[lba] = lst
        for k, s in set(lst):
            seen[(k, s)] += 1
    sigs = []                                    # 씬마다 서명 2개(둘 중 하나만 맞아도 인정) — 키 위치 원문이 어긋나는 레코드(~2%) 대비
    for lba in b9.SCENES_B9:
        cand = [(k, s) for k, s in per[lba] if seen[(k, s)] == 1]
        assert len(cand) >= 2, f"씬 {lba}: 고유 서명 후보 부족"
        first = cand[0]
        second = next((c for c in cand[1:] if (c[0] >> 13) != (first[0] >> 13)), cand[-1])   # 가능하면 다른 뱅크
        sigs.append((lba,) + first)
        sigs.append((lba,) + second)
    return sigs


def asm_rearm2(sigs) -> bytes:
    n = len(sigs)
    assert n <= 128
    a = Asm(REARM2)
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "go")
    a.emit(0x60)                                           # PRESENT≠0 → 그대로
    a.label("go")
    a.emit(0x43, 0x10, 0x48, 0x43, 0x08, 0x48)             # TMA4 PHA / TMA3 PHA (TMA3 은 대칭 유지용)
    a.emit(0xA5, 0x00, 0x48, 0xA5, 0x01, 0x48)             # $00/$01 보관
    a.emit(0xA2, n - 1)                                    # LDX #n-1
    a.label("loop")
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "BANKS")); a.emit(0, 0)
    a.emit(0x53, 0x10)                                     # TAM4 (씬 뱅크 → $8000)
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "ALO")); a.emit(0, 0)
    a.emit(0x85, 0x00)
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "AHI")); a.emit(0, 0)
    a.emit(0x85, 0x01)
    a.emit(0xC2)                                           # CLY
    for j in range(SIG_N):
        if j:
            a.emit(0xC8)                                   # INY
        a.emit(0xB1, 0x00, 0xDD); a.fixups.append((len(a.buf), "abs", f"SIG{j}")); a.emit(0, 0)
        a.branch(0xD0, "next")
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "RLO")); a.emit(0, 0)
    a.emit(0x85, 0x00)
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "RHI")); a.emit(0, 0)
    a.emit(0x85, 0x01)
    a.emit(0xA0, 41)
    a.label("cp")
    a.emit(0xB1, 0x00, 0x99, SCRATCH & 0xFF, SCRATCH >> 8, 0x88)   # LDA ($00),Y / STA SCRATCH,Y / DEY
    a.branch(0x10, "cp")
    a.emit(0xA9, 0x01, 0x8D, PRESENT & 0xFF, PRESENT >> 8)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.branch(0x80, "out")
    a.label("next")
    a.emit(0xCA)
    a.branch(0x30, "out")                                  # BMI out
    a.jmp("loop")
    a.label("out")
    a.emit(0x68, 0x85, 0x01, 0x68, 0x85, 0x00)
    a.emit(0x68, 0x53, 0x08, 0x68, 0x53, 0x10)             # PLA TAM3 / PLA TAM4
    a.emit(0x60)
    cols = {"BANKS": [], "ALO": [], "AHI": [], "RLO": [], "RHI": []}
    for j in range(SIG_N):
        cols[f"SIG{j}"] = []
    for lba, k, s in sigs:
        i = b9.SCENES_B9.index(lba)                  # 씬 테이블 번호
        addr = 0x8000 + (k & 0x1FFF)
        cols["BANKS"].append(0x68 + (k >> 13)); cols["ALO"].append(addr & 0xFF); cols["AHI"].append(addr >> 8)
        rp = TABLE_WIN + i * ENTRY_LEN + 2
        cols["RLO"].append(rp & 0xFF); cols["RHI"].append(rp >> 8)
        for j in range(SIG_N):
            cols[f"SIG{j}"].append(s[j])
    for name, vals in cols.items():
        a.label(name)
        a.emit(*vals)
    code = a.resolve()
    assert REARM2_OFF + len(code) <= REARM2_END, f"rearm2 {len(code)}B"
    return code


def main() -> None:
    sigs = pick_signatures()
    b37.main()
    card = bytearray(b37.OUT_CARD.read_bytes())
    # 씬 테이블 순서 = SCENES_B9 순서 확인
    for i, lba in enumerate(b9.SCENES_B9):
        o = CARD_TABLE_OFF + i * ENTRY_LEN
        assert (card[o] << 8 | card[o + 1]) == lba, f"씬 테이블 순서 불일치 {i}"
    code = asm_rearm2(sigs)
    o = REARM_BANK * 0x2000 + REARM2_OFF
    assert set(card[o:o + len(code)]) == {0xFF}, "rearm2 자리 비어 있지 않음"
    card[o:o + len(code)] = code
    b37.OUT_CARD.write_bytes(bytes(card))
    out = bytearray(b37.OUT_BIN.read_bytes())
    so = b7.eng_off(0xC89F)
    assert out[so + 3:so + 5] == bytes((0xA9, 0x3F)) and out[so + 7:so + 10] == bytes((0x20, 0x00, 0xAF)), "스텁 원본 불일치"
    out[so + 4] = REARM_BANK
    out[so + 8:so + 10] = bytes((REARM2 & 0xFF, REARM2 >> 8))
    b37.OUT_BIN.write_bytes(bytes(out))
    OUT_SIG.write_text(json.dumps({"format": "B38-REARM-SIGS", "sig_bytes": SIG_N,
                                   "scenes": [{"lba": l, "key": f"{k:05X}", "sig": s.hex().upper()} for l, k, s in sigs]},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": "B38_OK", "rearm2_bytes": len(code), "scenes": len(sigs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
