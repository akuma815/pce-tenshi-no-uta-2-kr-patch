#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B46 — **256KB 시스템 카드** (2단계: 허프만 대사 풀 + 공유 인덱스, 2026-10-11).

b45 와 같은 번역·디스크 패치. 카드는 뱅크 $00-$1F 만 쓴다(ares 외 Mesen2·Geargrafx·pce_fast 의 256KB 제한 대응).
구성:
  · 대사 풀: pool_huff (BPE 사전 + 정준 허프만, 레코드·사전 항목 바이트 정렬) — 1단계에서 빈 16x16 영역(뱅크 $08-$14),
    옛 12x12 꼬리($1B-$1F 빈 칸), BIOS 빈 칸(CDL cold)에 FFD 배치.
  · 인덱스: 씬 머리(매직 'H2' + 24 버킷 포인터) + 버킷(델타 1B[FF=절대 2B, FE=끝] + 뱅크·주소 3B + 원문길이-1 1B[FF=2B]).
    같은 내용의 버킷은 같은 뱅크 안에서 공유. 시작 주소 = 행 이미지 [4]=IBANK [5]=hi [6]=lo.
  · 디코더 뱅크 DEC_BANK($15): SERVE46($6000, MPR3) · ARMCHK46 · 정준 표(COUNT/SYMS) · 사전 주소표 ·
    조사 받침 비트표 · 조사 문자열 · 조사 게이트(MPR5 창 $A000+).
  · 창 리더(디스크) v46: armchk·serve 모두 MPR3 = DEC_BANK 브래킷. 조사 코드 A/B($1F)는 상수만 패치.
  · 재무장 v2(카드 $1F 머리)·폰트 압축·EX_GETFNT 패치는 b37/b38 그대로.
상태(창 스크래치 $C8C8+): FLAG 0=없음 1=원문(조사) 2=허프만 본문 3=사전 항목. 행 이미지 [6..] 은 로더가 씬 로드 때 FF 로 덮는다
(그때 FLAG=0). 출력: *_btrack_b46.bin/.cue + probes/SystemCard3_btrack_b46.pce (256KB)
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
import build_btrack_b45_hook_build as b45          # 경로·패치 설정(b28.PATCHES 등) 을 위해 먼저
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b36_hook_build as b36
import build_btrack_b28_hook_build as b28
import build_btrack_b9_hook_build as b9
import build_btrack_b7_hook_build as b7
import pool_huff as ph
from build_btrack_b7_hook_build import Asm, FLAG, TBANK, CURL, CURH, PRESENT, SCRATCH, CARD_TABLE_OFF, ENTRY_LEN

OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b46.bin"
OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b46.cue"
OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b46.pce"
OUT_LAYOUT = ROOT / "translation" / "btrack_b46_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = OUT_BIN, OUT_CUE, OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b46_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b46_rearm_signatures.json"

CARD256 = 0x40000
DEC_BANK = 0x15
W3, W5 = 0x6000, 0xA000                        # 디코더 뱅크를 MPR3 / MPR5 에 매핑했을 때의 기준
SAVEL, SAVEH, DBANK = 0xC8F6, 0xC8F7, 0xC8F8
KH = 0xC8FD                                    # armchk 키 hi (기존과 같은 칸)
IBANK_S, IBASEH_S, IBASEL_S = SCRATCH + 4, SCRATCH + 5, SCRATCH + 6
BITBUF, BITCNT, SBUF, SCNT, PEND = (SCRATCH + i for i in range(8, 13))
CODEL, CODEH, FIRSTL, FIRSTH, IDXL, IDXH = (SCRATCH + i for i in range(13, 19))
SYML, SYMH, TL, TH = SCRATCH + 19, SCRATCH + 20, SCRATCH + 22, SCRATCH + 23
CKL, CKH = SCRATCH + 24, SCRATCH + 25
MAGIC = bytes((0x48, 0x33))                    # 'H3' (머리 = 매직 + 24 × [뱅크, 주소 lo, hi])
HEAD_LEN = 2 + 24 * 3
# 디코더 뱅크 배치(뱅크 안 오프셋)
OFF_SERVE, OFF_ARMCHK, OFF_TABS, OFF_BITS, OFF_PART, OFF_GATE, OFF_SYMS = 0x0000, 0x0200, 0x0400, 0x0500, 0x0700, 0x0740, 0x0800
SERVE46, ARMCHK46 = W3 + OFF_SERVE, W3 + OFF_ARMCHK
CNTL_T, CNTH_T, MASK_T3 = W3 + OFF_TABS, W3 + OFF_TABS + 0x20, W3 + OFF_TABS + 0x40
MASK_T5 = W5 + OFF_TABS + 0x40                 # 조사 게이트(MPR5 창)용 같은 표
GATE46 = W5 + OFF_GATE
BIOS_RUNS = [(0x01, 0x0CF9, 0x1C77), (0x01, 0x1C7A, 0x2000), (0x02, 0x1F46, 0x2000), (0x03, 0x1A50, 0x2000), (0x16, 0x159E, 0x2000)]


# ---------------------------------------------------------------- 6502 코드
def asm_reader_v46(origin: int) -> Asm:
    a = Asm(origin)
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)                             # TMA5 PHA
    a.emit(0xAD, IBANK_S & 0xFF, IBANK_S >> 8, 0x53, 0x20)   # MPR5 = IBANK
    a.emit(0x43, 0x08, 0x48)                             # TMA3 PHA
    a.emit(0xA9, DEC_BANK, 0x53, 0x08)                   # MPR3 = DEC_BANK
    a.jsr(ARMCHK46)
    a.emit(0x68, 0x53, 0x08)
    a.emit(0x68, 0x53, 0x20)
    a.branch(0xB0, "native")
    a.label("serve")
    a.emit(0x43, 0x08, 0x48)
    a.emit(0xA9, DEC_BANK, 0x53, 0x08)
    a.jsr(SERVE46)
    a.emit(0x68, 0x53, 0x08)
    a.emit(0x60)
    a.label("native")
    a.emit(0x38, 0x60)
    assert len(a.buf) <= b28.READER_V3M_LEN
    a.emit(*([0xFF] * (b28.READER_V3M_LEN - len(a.buf))))
    return a


def st(a, addr): a.emit(0x8D, addr & 0xFF, addr >> 8)
def ld(a, addr): a.emit(0xAD, addr & 0xFF, addr >> 8)
def stz(a, addr): a.emit(0x9C, addr & 0xFF, addr >> 8)


def asm_serve46(syms_w3: int, dpt_w3: int) -> bytes:
    a = Asm(SERVE46)
    a.emit(0xDA, 0x5A, 0x43, 0x20, 0x48)                 # PHX PHY TMA5 PHA
    ld(a, FLAG); a.emit(0xC9, 0x01); a.branch(0xD0, "huff")
    # --- 원문(조사 문자열) ---
    ld(a, TBANK); a.emit(0x53, 0x20)
    a.jsr("rdcur"); a.branch(0xD0, "rawok"); a.jmp("nul")
    a.label("rawok")
    a.jsr("inc1"); a.jmp("out")
    a.label("huff")
    ld(a, PEND); a.branch(0xF0, "np")
    stz(a, PEND); a.jmp("out")
    a.label("np")
    ld(a, TBANK); a.emit(0x53, 0x20)
    a.label("again")
    a.jsr("decode")
    ld(a, SYMH); a.emit(0x0D, SYML & 0xFF, SYML >> 8)    # ORA SYML
    a.branch(0xD0, "notend")
    ld(a, FLAG); a.emit(0xC9, 0x03); a.branch(0xF0, "dend"); a.jmp("nul")
    a.label("dend")
    # 사전 항목 끝 → 본문 복귀
    ld(a, SAVEL); st(a, CURL); ld(a, SAVEH); st(a, CURH); ld(a, DBANK); st(a, TBANK); a.emit(0x53, 0x20)
    ld(a, SBUF); st(a, BITBUF); ld(a, SCNT); st(a, BITCNT)
    a.emit(0xA9, 0x02); st(a, FLAG)
    a.jmp("again")
    a.label("notend")
    ld(a, SYMH); a.emit(0xC9, 0xF0); a.branch(0x90, "chr")
    # 사전 항목: 본문 상태 보관 → 항목 주소(DPT + id*3)
    ld(a, CURL); st(a, SAVEL); ld(a, CURH); st(a, SAVEH); ld(a, TBANK); st(a, DBANK)
    ld(a, BITBUF); st(a, SBUF); ld(a, BITCNT); st(a, SCNT)
    ld(a, SYML); a.emit(0x85, 0x00); ld(a, SYMH); a.emit(0x29, 0x0F, 0x85, 0x01)   # id
    # t = id*2 → $00/$01 *3 = id*2 + id
    a.emit(0xA5, 0x00); st(a, TL); a.emit(0xA5, 0x01); st(a, TH)
    a.emit(0x06, 0x00, 0x26, 0x01)                       # ASL $00 ROL $01 (id*2)
    a.emit(0x18, 0xA5, 0x00, 0x6D, TL & 0xFF, TL >> 8, 0x85, 0x00)
    a.emit(0xA5, 0x01, 0x6D, TH & 0xFF, TH >> 8, 0x85, 0x01)       # id*3
    a.emit(0x18, 0xA5, 0x00, 0x69, dpt_w3 & 0xFF, 0x85, 0x00)
    a.emit(0xA5, 0x01, 0x69, dpt_w3 >> 8, 0x85, 0x01)
    a.emit(0xA0, 0x00, 0xB1, 0x00); st(a, TBANK)
    a.emit(0xC8, 0xB1, 0x00); st(a, CURL)
    a.emit(0xC8, 0xB1, 0x00); st(a, CURH)
    stz(a, BITCNT)
    a.emit(0xA9, 0x03); st(a, FLAG)
    ld(a, TBANK); a.emit(0x53, 0x20)
    a.jmp("again")
    a.label("chr")
    ld(a, SYMH); a.branch(0xF0, "one")
    ld(a, SYML); st(a, PEND); ld(a, SYMH); a.jmp("out")
    a.label("one")
    ld(a, SYML)
    a.label("out")
    a.emit(0x8D, 0x80, 0x2D)                             # STA $2D80
    a.emit(0x68, 0x53, 0x20, 0x7A, 0xFA, 0x18, 0x60)     # PLA TAM5 PLY PLX CLC RTS
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)
    stz(a, FLAG)
    a.emit(0x7A, 0xFA, 0x38, 0x60)
    # --- 공용 ---
    a.label("rdcur")
    ld(a, CURL); a.emit(0x85, 0x00); ld(a, CURH); a.emit(0x85, 0x01)
    a.emit(0xB2, 0x00, 0x60)
    a.label("inc1")
    a.emit(0xEE, CURL & 0xFF, CURL >> 8); a.branch(0xD0, "i1r"); a.emit(0xEE, CURH & 0xFF, CURH >> 8)
    a.label("i1r"); a.emit(0x60)
    a.label("getbit")                                    # C = 다음 비트
    ld(a, BITCNT); a.branch(0xD0, "gb1")
    a.jsr("rdcur"); st(a, BITBUF); a.jsr("inc1")
    a.emit(0xA9, 0x08); st(a, BITCNT)
    a.label("gb1")
    a.emit(0xCE, BITCNT & 0xFF, BITCNT >> 8)             # DEC BITCNT
    a.emit(0x0E, BITBUF & 0xFF, BITBUF >> 8)             # ASL BITBUF → C
    a.emit(0x60)
    # --- 정준 허프만 기호 하나 (puff) ---
    a.label("decode")
    for v in (CODEL, CODEH, FIRSTL, FIRSTH, IDXL, IDXH):
        stz(a, v)
    a.emit(0xA2, 0x01)                                   # LDX #1 (길이)
    a.label("dloop")
    a.emit(0xDA); a.jsr("getbit"); a.emit(0xFA)          # PHX JSR getbit PLX (C 보존: PLX 는 C 무관)
    a.emit(0x2E, CODEL & 0xFF, CODEL >> 8, 0x2E, CODEH & 0xFF, CODEH >> 8)   # ROL CODEL ROL CODEH
    a.emit(0x18); ld(a, FIRSTL); a.emit(0x7D, CNTL_T & 0xFF, CNTL_T >> 8); st(a, TL)
    ld(a, FIRSTH); a.emit(0x7D, CNTH_T & 0xFF, CNTH_T >> 8); st(a, TH)       # T = first + count
    a.branch(0xB0, "found")                                                  # T ≥ 65536(16비트 부호, 부호 공간 꽉 참) → 항상 code < T
    ld(a, CODEH); a.emit(0xCD, TH & 0xFF, TH >> 8); a.branch(0x90, "found"); a.branch(0xD0, "notf")
    ld(a, CODEL); a.emit(0xCD, TL & 0xFF, TL >> 8); a.branch(0x90, "found")
    a.label("notf")
    a.emit(0x18); ld(a, IDXL); a.emit(0x7D, CNTL_T & 0xFF, CNTL_T >> 8); st(a, IDXL)
    ld(a, IDXH); a.emit(0x7D, CNTH_T & 0xFF, CNTH_T >> 8); st(a, IDXH)
    ld(a, TL); a.emit(0x0A); st(a, FIRSTL); ld(a, TH); a.emit(0x2A); st(a, FIRSTH)   # first = T << 1
    a.emit(0xE8, 0xE0, ph.MAXLEN + 1); a.branch(0x90, "dloop")
    stz(a, SYML); stz(a, SYMH); a.emit(0x60)             # 잘못된 부호 → EOS 취급
    a.label("found")
    a.emit(0x38); ld(a, CODEL); a.emit(0xED, FIRSTL & 0xFF, FIRSTL >> 8); st(a, TL)
    ld(a, CODEH); a.emit(0xED, FIRSTH & 0xFF, FIRSTH >> 8); st(a, TH)
    a.emit(0x18); ld(a, TL); a.emit(0x6D, IDXL & 0xFF, IDXL >> 8); st(a, TL)
    ld(a, TH); a.emit(0x6D, IDXH & 0xFF, IDXH >> 8); st(a, TH)
    a.emit(0x0E, TL & 0xFF, TL >> 8, 0x2E, TH & 0xFF, TH >> 8)                  # *2
    a.emit(0x18); ld(a, TL); a.emit(0x69, syms_w3 & 0xFF, 0x85, 0x00)
    ld(a, TH); a.emit(0x69, syms_w3 >> 8, 0x85, 0x01)
    a.emit(0xA0, 0x00, 0xB1, 0x00); st(a, SYML)
    a.emit(0xC8, 0xB1, 0x00); st(a, SYMH)
    a.emit(0x60)
    code = a.resolve()
    assert OFF_SERVE + len(code) <= OFF_ARMCHK, f"serve46 {len(code)}B"
    return code


def asm_armchk46() -> bytes:
    """armchk_v5 의 kb 계산부 그대로 + 새 인덱스 형식."""
    a = Asm(ARMCHK46)
    a.emit(0xDA, 0x5A)                                   # PHX PHY
    a.emit(0xA5, 0x53); a.branch(0xD0, "p0")
    a.emit(0xAD, 0x69, 0x2E); a.branch(0xF0, "dflt")
    a.emit(0x18, 0x6D, 0xD0, 0x22, 0x38, 0xE9, 0x68, 0xC9, 0x18); a.branch(0xB0, "p0")
    a.emit(0xAA)
    a.emit(0xA5, 0x4C, 0xC9, 0xC0); a.branch(0x90, "p0")
    a.emit(0xC9, 0xE0); a.branch(0xB0, "p0")
    a.branch(0x80, "common")
    a.label("dflt")
    a.emit(0xA5, 0x4C, 0xC9, 0x80); a.branch(0x90, "p0")
    a.emit(0xC9, 0xE0); a.branch(0xB0, "p0")
    a.emit(0x4A, 0x4A, 0x4A, 0x4A, 0x4A, 0x18, 0x69, 0x08, 0x6D, 0xD0, 0x22, 0x38, 0xE9, 0x68, 0xC9, 0x18)
    a.branch(0xB0, "p0")
    a.emit(0xAA)
    a.label("common")                                    # X = kb
    ld(a, IBASEL_S); a.emit(0x85, 0x00); ld(a, IBASEH_S); a.emit(0x85, 0x01)
    a.emit(0xA0, 0x00, 0xB1, 0x00, 0xC9, MAGIC[0]); a.branch(0xD0, "p0")
    a.emit(0xC8, 0xB1, 0x00, 0xC9, MAGIC[1]); a.branch(0xD0, "p0")
    a.branch(0x80, "cont")
    a.label("p0")
    a.jmp("pass")
    a.label("cont")
    a.emit(0xA5, 0x4C, 0x29, 0x1F); st(a, KH)
    a.emit(0x8A); st(a, TL)                              # TXA STA TL (kb)
    a.emit(0x0A, 0x18, 0x6D, TL & 0xFF, TL >> 8, 0x69, 0x02, 0xA8)   # Y = kb*3 + 2
    a.emit(0xB1, 0x00, 0x48, 0xC8, 0xB1, 0x00, 0x48)                 # 뱅크 PHA, lo PHA
    a.emit(0xC8, 0xB1, 0x00, 0x85, 0x01, 0x68, 0x85, 0x00)           # hi → $01, lo → $00
    a.emit(0x68, 0x53, 0x20)                                         # PLA TAM5 (버킷 뱅크; 리더가 끝에 MPR5 복원)
    stz(a, CKL); stz(a, CKH)
    a.label("loop")
    a.emit(0xB2, 0x00)                                   # LDA ($00) = d
    a.emit(0xC9, 0xFE); a.branch(0xF0, "p1"); a.branch(0xB0, "absol")
    a.emit(0x18, 0x6D, CKL & 0xFF, CKL >> 8); st(a, CKL)
    a.branch(0x90, "d1"); a.emit(0xEE, CKH & 0xFF, CKH >> 8)
    a.label("d1")
    a.emit(0xA9, 0x01); a.jsr("addp")
    a.branch(0x80, "cmp")
    a.label("p1")
    a.jmp("pass")
    a.label("absol")
    a.emit(0xA0, 0x01, 0xB1, 0x00); st(a, CKH)
    a.emit(0xC8, 0xB1, 0x00); st(a, CKL)
    a.emit(0xA9, 0x03); a.jsr("addp")
    a.label("cmp")
    ld(a, CKH); a.emit(0xCD, KH & 0xFF, KH >> 8); a.branch(0x90, "skip"); a.branch(0xD0, "p1")
    ld(a, CKL); a.emit(0xC5, 0x4B); a.branch(0x90, "skip"); a.branch(0xD0, "p1")
    # --- 일치 ---
    a.emit(0xA0, 0x00, 0xB1, 0x00); st(a, TBANK)
    a.emit(0xC8, 0xB1, 0x00); st(a, CURL)
    a.emit(0xC8, 0xB1, 0x00); st(a, CURH)
    a.emit(0xC8, 0xB1, 0x00, 0xC9, 0xFF); a.branch(0xF0, "big")
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B); a.branch(0x90, "arm"); a.emit(0xE6, 0x4C)
    a.branch(0x80, "arm")
    a.label("big")
    a.emit(0xC8, 0xB1, 0x00, 0x18, 0x65, 0x4B, 0x85, 0x4B)
    a.emit(0xC8, 0xB1, 0x00, 0x65, 0x4C, 0x85, 0x4C)
    a.label("arm")
    a.emit(0xA9, 0x02); st(a, FLAG)
    stz(a, BITCNT); stz(a, PEND)
    a.emit(0x7A, 0xFA, 0x18, 0x60)
    a.label("skip")
    a.emit(0xA0, 0x03, 0xB1, 0x00, 0xC9, 0xFF); a.branch(0xD0, "s4")
    a.emit(0xA9, 0x06); a.jsr("addp"); a.jmp("loop")
    a.label("s4")
    a.emit(0xA9, 0x04); a.jsr("addp"); a.jmp("loop")
    a.label("pass")
    a.emit(0x7A, 0xFA, 0x38, 0x60)
    a.label("addp")                                      # ($00/$01) += A
    a.emit(0x18, 0x65, 0x00, 0x85, 0x00); a.branch(0x90, "ar"); a.emit(0xE6, 0x01)
    a.label("ar"); a.emit(0x60)
    code = a.resolve()
    assert OFF_ARMCHK + len(code) <= OFF_TABS, f"armchk46 {len(code)}B"
    return code


def asm_gate46() -> bytes:
    """b28 asm_josa_gate 와 같은 흐름, 받침 조회만 비트표(13행×32B)로."""
    a = Asm(GATE46)
    a.emit(0x8A, 0x48, 0xBA)                             # TXA PHA TSX
    a.emit(0xBD, 0x0A, 0x21, 0xC9, b28.PRINTER_RET & 0xFF); a.branch(0xD0, "no2")
    a.emit(0xBD, 0x0B, 0x21, 0xC9, b28.PRINTER_RET >> 8); a.branch(0xD0, "no2")
    a.emit(0xAD, b28.LASTHI & 0xFF, b28.LASTHI >> 8, 0xC9, 0x88); a.branch(0x90, "no2")
    a.emit(0xC9, b28.ONEBYTE_ROW_HI + 1); a.branch(0xB0, "no2")
    a.emit(0x38, 0xE9, 0x88)                             # row = LASTHI - $88
    a.emit(0x48, 0x4A, 0x4A, 0x4A, 0x18, 0x69, (W5 + OFF_BITS) >> 8, 0x85, 0x01)   # $01 = BITS_HI + row>>3
    a.emit(0x68, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x85, 0x00)                           # $00 = (row<<5)&$FF
    a.emit(0xAD, b28.LASTLO & 0xFF, b28.LASTLO >> 8, 0x4A, 0x4A, 0x4A, 0x18, 0x65, 0x00, 0x85, 0x00)
    a.branch(0x90, "c1"); a.emit(0xE6, 0x01)
    a.label("c1")
    a.emit(0xAD, b28.LASTLO & 0xFF, b28.LASTLO >> 8, 0x29, 0x07, 0xAA)   # X = bit (원 게이트처럼 Y 보존; X 는 josa A 가 PHX 해 둠)
    a.emit(0xB2, 0x00, 0x3D, MASK_T5 & 0xFF, MASK_T5 >> 8)          # LDA ($00) AND MASK,X
    a.branch(0xF0, "z")
    a.emit(0xA9, 0x01)
    a.label("z")
    a.emit(0x85, 0x00, 0x68, 0x05, 0x00)                 # STA $00 PLA ORA $00 → idx
    a.jmp(b28.JOSA_B)
    a.label("no2")
    a.emit(0x68)
    a.jmp(b28.JOSA_GNO)
    code = a.resolve()
    assert OFF_GATE + len(code) <= OFF_SYMS
    return code


# ---------------------------------------------------------------- 데이터
def records():
    rows = [(lba, int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little"), r["encoded_hex"], r["original_raw_length"])
            for lba in b9.SCENES_B9 for r in b36._orig_payload(lba)]
    return rows


def free_regions(card: bytes, info12_end: int, info: dict | None = None):
    regs = [(b, 0, 0x2000) for b in range(0x08, DEC_BANK)]
    # $1B-$1E: 폰트 저장소 끝(info12_end) ~ 표 앞, 표 뒤 ~ 뱅크 끝. (b58) 표 위치·크기를 font_compact 정보에서 — 크레딧 한자로 저장소가 커지면 표가 다음 뱅크로 밀린다
    tab_lo = (info or {}).get("tab_bank", 0x1C) * 0x2000
    tab_hi = tab_lo + (info or {}).get("tab_size", 0x800)
    for b in range(0x1B, 0x1F):
        lo, hi = b * 0x2000, (b + 1) * 0x2000
        for s, e in ((max(lo, info12_end), min(hi, tab_lo)), (max(lo, tab_hi, info12_end), hi)):
            if s < e:
                regs.append((b, s - lo, e - lo))
    regs += [(0x1F, None, CARD_TABLE_OFF - 0x1F * 0x2000)]
    regs += BIOS_RUNS
    out = []
    for b, s, e in regs:
        if s is None:     # $1F: 재무장 v2 뒤
            o = 0x1F * 0x2000
            s = len(card[o:o + e].rstrip(b"\xFF")) + 0x10
        lo, hi = b * 0x2000 + s, b * 0x2000 + e
        seg = card[lo:hi]
        assert set(seg) <= {0xFF} or set(seg) <= {0x00}, f"빈 영역 아님 {b:02X}:{s:04X}-{e:04X} {sorted(set(seg))[:5]}"
        out.append([b, s, e])
    return out


def build_indexes(rows, place_text):
    """씬별 인덱스(머리 + 버킷) 바이트. place_text(h) → (bank, addr)."""
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for lba, k, h, n in rows:
        per[lba][k >> 13].append((k & 0x1FFF, h, n))
    scenes = {}
    for lba in b9.SCENES_B9:
        buckets = []
        for kb in range(24):
            ents = sorted(per[lba].get(kb, []))
            out = bytearray(); prev = 0
            for o, h, n in ents:
                d = o - prev; prev = o
                if d < 0xFE:
                    out.append(d)
                else:
                    out += bytes((0xFF, o >> 8, o & 0xFF))
                bank, addr = place_text(h)
                out += bytes((bank, addr & 0xFF, addr >> 8))
                lm1 = n - 1
                out += bytes((lm1,)) if lm1 < 0xFF else bytes((0xFF, lm1 & 0xFF, lm1 >> 8))
            out.append(0xFE)
            buckets.append(bytes(out))
        scenes[lba] = buckets
    return scenes


def main() -> None:
    rows = records()
    # 0) 압축
    hf = ph.build([h for _, _, h, _ in rows])
    print(f"[b46] huffman text={sum(len(v) for v in hf['rec'].values())} dict={sum(len(x) for x in hf['dict'])} "
          f"syms={len(hf['symbols'])} n_dict={hf['n_dict']}", flush=True)
    # 1) b45 구성으로 디스크·512KB 카드 생성 (리더만 v46)
    b36.asm_reader_v36 = asm_reader_v46
    b38.main()
    card512 = OUT_CARD.read_bytes()
    card = bytearray(card512[:CARD256])
    info = json.loads(b37.OUT_INFO.read_text(encoding="utf-8"))
    end16 = info["base16"] + info["store16"]
    regs = free_regions(card, (end16 + 0xF) & ~0xF, info)
    cap = sum(e - s for _, s, e in regs)
    # 2) 디코더 뱅크 이미지
    dec = bytearray(b"\xFF" * 0x2000)
    syms = hf["symbols"]; syms_off = OFF_SYMS
    syms_bytes = b"".join(bytes((s & 0xFF, s >> 8)) for s in syms)
    dpt_off = (syms_off + len(syms_bytes) + 0xF) & ~0xF
    assert dpt_off + 3 * hf["n_dict"] <= 0x2000, "디코더 뱅크 초과"
    dec[syms_off:syms_off + len(syms_bytes)] = syms_bytes
    counts = hf["counts"]
    for i in range(ph.MAXLEN + 1):
        dec[OFF_TABS + i] = counts[i] & 0xFF; dec[OFF_TABS + 0x20 + i] = counts[i] >> 8
    dec[OFF_TABS + 0x40:OFF_TABS + 0x48] = bytes(1 << k for k in range(8))
    # 받침 비트표 + 조사 문자열 (b28 표 + b34 「를　」 형식)
    asg = json.loads(b28.ASSIGN.read_text(encoding="utf-8"))["assignment"]
    omap = json.loads(b28.ONEBYTE.read_text(encoding="utf-8"))["map"]
    bits = bytearray(13 * 32)
    def batchim(ch): return 1 if (ord(ch) - 0xAC00) % 28 else 0
    for ch, e in asg.items():
        lead, trail = int(e["sjis"][:2], 16), int(e["sjis"][2:], 16)
        if batchim(ch): bits[(lead - 0x88) * 32 + (trail >> 3)] |= 1 << (trail & 7)
    for code, v in omap.items():
        c = int(code, 16)
        if batchim(v["ch"]): bits[(b28.ONEBYTE_ROW_HI - 0x88) * 32 + (c >> 3)] |= 1 << (c & 7)
    dec[OFF_BITS:OFF_BITS + len(bits)] = bits
    part = bytearray(64)                                 # idx = 종류*2 + 받침, 8B 칸 (b28 배치 + b34 「를　」 형식)
    for t, (yes, no) in enumerate(b28.TYPES):
        for b, p in ((1, yes), (0, no)):
            enc = b"".join(bytes.fromhex(asg[c]["sjis"]) for c in p) + bytes((0x81, 0x40, 0x00))
            o = (t * 2 + b) * 8
            part[o:o + len(enc)] = enc
    dec[OFF_PART:OFF_PART + 64] = part
    gate = asm_gate46(); dec[OFF_GATE:OFF_GATE + len(gate)] = gate
    arm = asm_armchk46()
    dec[OFF_ARMCHK:OFF_ARMCHK + len(arm)] = arm
    # 3) 배치 (FFD): 텍스트 레코드·사전 항목·고유 버킷(전 씬 공유)·씬 머리(74B) — 크기만으로 결정(주소 3B 고정)
    placed: dict[str, tuple[int, int]] = {}
    dict_pos: list = [None] * hf["n_dict"]
    tid = {h: i for i, h in enumerate(sorted(hf["rec"]))}
    probe = build_indexes(rows, lambda h: (tid[h] >> 16, 0xA000 + (tid[h] & 0xFFFF)))   # 텍스트마다 다른 가짜 주소 → 버킷 동일성 = 내용 동일성
    uniq_b = {}
    for lba in b9.SCENES_B9:
        for bk in probe[lba]:
            uniq_b.setdefault(bk, len(uniq_b))
    dpt_end = dpt_off + 3 * hf["n_dict"]
    regs.append([DEC_BANK, (dpt_end + 0xF) & ~0xF, 0x2000])
    items = [(len(hf["rec"][h]), "r", h) for h in hf["rec"]] + [(len(x), "d", i) for i, x in enumerate(hf["dict"])]
    items += [(len(bk), "b", i) for bk, i in uniq_b.items()] + [(HEAD_LEN, "h", lba) for lba in b9.SCENES_B9]
    items.sort(key=lambda t: (-t[0], t[1], str(t[2])))
    print(f"[b46] 용량 {sum(e - s for _, s, e in regs)}B / 필요 {sum(t[0] for t in items)}B "
          f"(인덱스 = 고유 버킷 {len(uniq_b)}개 {sum(len(b) for b in uniq_b)}B + 머리 {HEAD_LEN * len(b9.SCENES_B9)}B), "
          f"디코더 뱅크 사용 {dpt_end}B", flush=True)
    pos = {}
    for size, kind, key in items:
        for r in regs:
            if r[2] - r[1] >= size:
                pos[(kind, key)] = (r[0], r[1]); r[1] += size
                break
        else:
            raise SystemExit(f"[b46] 배치 실패: {kind} {size}B — 용량 부족")
    def put(bank, off, data):
        o = bank * 0x2000 + off
        assert set(card[o:o + len(data)]) <= {0xFF, 0x00}, f"덮어쓰기 {bank:02X}:{off:04X}"
        card[o:o + len(data)] = data
    for h, data in hf["rec"].items():
        b, off = pos[("r", h)]; put(b, off, data); placed[h] = (b, W5 + off)
    for i, data in enumerate(hf["dict"]):
        b, off = pos[("d", i)]; put(b, off, data); dict_pos[i] = (b, W5 + off)
    dpt = b"".join(bytes((b, a & 0xFF, a >> 8)) for b, a in dict_pos)
    dec[dpt_off:dpt_off + len(dpt)] = dpt
    serve = asm_serve46(W3 + syms_off, W3 + dpt_off)
    dec[OFF_SERVE:OFF_SERVE + len(serve)] = serve
    o = DEC_BANK * 0x2000
    keep = bytes(card[o + ((dpt_end + 0xF) & ~0xF):o + 0x2000])          # 디코더 뱅크 남은 칸에 배치된 데이터 보존
    card[o:o + 0x2000] = dec
    card[o + ((dpt_end + 0xF) & ~0xF):o + 0x2000] = keep
    # 4) 버킷(실주소) + 씬 머리 + 씬 테이블 행
    idx = build_indexes(rows, lambda h: placed[h])
    real_pos = {}
    for lba in b9.SCENES_B9:
        for pb, rb in zip(probe[lba], idx[lba]):
            assert len(pb) == len(rb)
            bpos = pos[("b", uniq_b[pb])]
            if pb in real_pos:
                assert real_pos[pb][1] == rb, "같은 가짜 버킷이 다른 실버킷으로"
            else:
                real_pos[pb] = (bpos, rb); put(bpos[0], bpos[1], rb)
    loc = {}
    for lba in b9.SCENES_B9:
        head = bytearray(MAGIC)
        for pb in probe[lba]:
            (bb, boff), _ = real_pos[pb]
            a5 = W5 + boff
            head += bytes((bb, a5 & 0xFF, a5 >> 8))
        assert len(head) == HEAD_LEN
        hb, hoff = pos[("h", lba)]
        put(hb, hoff, bytes(head)); loc[lba] = (hb, W5 + hoff)
    for i, lba in enumerate(b9.SCENES_B9):
        t = CARD_TABLE_OFF + i * ENTRY_LEN
        assert (card[t] << 8 | card[t + 1]) == lba
        bank, base = loc[lba]
        card[t + 2 + 4] = bank; card[t + 2 + 5] = base >> 8; card[t + 2 + 6] = base & 0xFF
    idx_banks = []
    # 5) 조사 코드 A/B 상수 패치 ($1F 꼬리)
    ja, jb = b28.JOSA_A_CARD, b28.JOSA_B_CARD
    seg = card[ja:ja + 100]
    i = seg.index(bytes((0xA9, 0x3F, 0x53, 0x20, 0x4C, 0x00, 0xAE)))
    card[ja + i + 1] = DEC_BANK; card[ja + i + 5] = GATE46 & 0xFF; card[ja + i + 6] = GATE46 >> 8
    seg = card[jb:jb + 30]
    i = seg.index(bytes((0xA9, 0xAD, 0x8D))); card[jb + i + 1] = (W5 + OFF_PART) >> 8
    i = seg.index(bytes((0xA9, 0x3F, 0x8D))); card[jb + i + 1] = DEC_BANK
    OUT_CARD.write_bytes(bytes(card))
    n = verify_model(bytes(card), rows, hf)
    used = {f"{b:02X}": (s, e) for b, s, e in regs}
    OUT_LAYOUT.write_text(json.dumps({"format": "B46-CARD-LAYOUT", "dec_bank": f"{DEC_BANK:02X}",
                                      "unique_buckets": len(uniq_b),
                                      "region_left": {f"{b:02X}:{s:04X}": e - s for b, s, e in regs},
                                      "verified_entries": n, "serve_bytes": len(serve), "armchk_bytes": len(arm),
                                      "gate_bytes": len(gate), "card_size": len(card)}, ensure_ascii=False, indent=1), encoding="utf-8")
    left = sum(e - s for _, s, e in regs)
    print(json.dumps({"status": "B46_OK", "card": OUT_CARD.name, "size": len(card), "verified": n, "free_left": left,
                      "unique_buckets": len(uniq_b)}, ensure_ascii=False))


def verify_model(card: bytes, rows, hf) -> int:
    """카드 바이트만으로: 씬 테이블 → 인덱스 → 허프만 디코드(카드의 COUNT/SYMS/사전 주소표) = 원문(압축 전) 전수."""
    def rd(bank, addr):
        assert addr >= W5 and bank < 0x20
        return card[bank * 0x2000 + addr - W5]
    dec = card[DEC_BANK * 0x2000:(DEC_BANK + 1) * 0x2000]
    counts = [dec[OFF_TABS + i] | dec[OFF_TABS + 0x20 + i] << 8 for i in range(ph.MAXLEN + 1)]
    nsym = sum(counts)
    syms = [dec[OFF_SYMS + 2 * k] | dec[OFF_SYMS + 2 * k + 1] << 8 for k in range(nsym)]
    dpt_off = (OFF_SYMS + 2 * nsym + 0xF) & ~0xF
    model = {"counts": counts, "symbols": syms}
    def stream(bank, addr):
        class R:
            def __getitem__(s, i): return rd(bank, addr + i)
        return R()
    def dget(d):
        b, lo, hi = dec[dpt_off + 3 * d:dpt_off + 3 * d + 3]
        return bytes(rd(b, (hi << 8 | lo) + i) for i in range(64))
    want = {(lba, k): (bytes.fromhex(h), n) for lba, k, h, n in rows}
    cnt = 0
    for i, lba in enumerate(b9.SCENES_B9):
        t = CARD_TABLE_OFF + i * ENTRY_LEN + 2
        hb, base = card[t + 4], card[t + 5] << 8 | card[t + 6]
        assert rd(hb, base) == MAGIC[0] and rd(hb, base + 1) == MAGIC[1]
        for kb in range(24):
            bank = rd(hb, base + 2 + kb * 3)
            p = rd(hb, base + 3 + kb * 3) | rd(hb, base + 4 + kb * 3) << 8
            cur = 0
            while True:
                d = rd(bank, p)
                if d == 0xFE: break
                if d == 0xFF: cur = rd(bank, p + 1) << 8 | rd(bank, p + 2); p += 3
                else: cur += d; p += 1
                tb, ta = rd(bank, p), rd(bank, p + 1) | rd(bank, p + 2) << 8
                l1 = rd(bank, p + 3)
                if l1 == 0xFF: l1 = rd(bank, p + 4) | rd(bank, p + 5) << 8; p += 6
                else: p += 4
                key = kb << 13 | cur
                exp, n = want[(lba, key)]
                data = bytes(rd(tb, ta + j) for j in range(min(4096, 0xC000 - ta)))
                got = ph.decode_bytes(data, model, dget)
                assert got == exp, f"scene {lba} key {key:05X} 디코드 불일치"
                assert l1 == n - 1
                cnt += 1
    assert cnt == len(want), (cnt, len(want))
    return cnt


if __name__ == "__main__":
    main()
