#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B7 — 다중 씬 확대 (b6 구조 + 카드 씬 테이블 + 로더 훅 v3).

b6 대비 변경 (2026-08-23 설계, HANDOFF §1 b7-알파):
  - 씬별 풀: 균일 14섹터 (base+0 ×12 → $7C/$7D/$7E, base+12 ×2 → $6D전반).
    482@9178(=b6 동일)·290@9192·2882@9206 — 기존 트랙 끝 여유 내.
  - 씬 테이블은 카드 폰트 꼬리 free(0x3F054, slot 3418+ FF 실측)에 배치:
    엔트리 6B = (lba_hi,mid,lo, base_hi,mid,lo), 종결 FF.
    출력 카드 = probes/SystemCard3_btrack_b7.pce (btrack_full + 테이블).
  - 로더 훅 v3: mode-06 로드마다 MPR5=$1F(카드) 브래킷으로 테이블 검색.
    매치 → 원본 로드 후 풀 행(산술 계산→창 스크래치) 적재, cur scene 저장,
    PRESENT=1. 비매치+PRESENT=1 → cur scene 에서 복원 행 계산 후 적재,
    PRESENT=0. 정적 행 테이블 제거.
  - 리더(트램펄린/디스패치/serve/armchk)·이설 슬라이스·벡터 = b6 그대로.

전제 실측: 카드 ROM 뱅크 $00-$1F 는 상시 어드레스 공간(BIOS 매핑 구조),
0x3F054 구간 FF·미배정, $7C-$7F/$6D 는 482 컨텍스트 CDL cold (타 씬은
게이트+씬별 CDL 부채로 검증).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
SRC_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
SRC_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
CARD_SRC = ROOT / "probes" / "SystemCard3_btrack_full.pce"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b7.pce"
DISASM = ROOT / "tools" / "huc6280_disasm_verifier" / "bin" / "Debug" / "net8.0" / "huc6280_disasm_verifier.exe"

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b7"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "btrack_b7_hook_manifest.json"

T2 = 7_914_480
ENG = T2 + 258 * 2048


def eng_off(logical: int) -> int:
    assert 0x4000 <= logical < 0xE000
    return ENG + (logical - 0x4000)


# ---- 배치 상수 (b6 계승) -----------------------------------------------------

VECTOR = 0x4036
SLICE_LO, SLICE_HI = 0x66DA, 0x6704
SLICE_JSR_E009 = 0x66FC
TRAMP = 0x66DF

WINDOW_LO = 0xC737
LOADER = 0xC737

# 스크래치·상태 (창 끝). 행 셋 2벌×21B: 풀(+0..20), 복원(+21..41) — 카드에서 복사.
SCRATCH = 0xC8C8                    # ..$C8F1 (42B) — FLAG($C8F9) 앞까지 여유 ✓
RESTORE_OFF = 21
WINDOW_CODE_END = SCRATCH
FLAG, TBANK, CURL, CURH = 0xC8F9, 0xC8FA, 0xC8FB, 0xC8FC
PRESENT = 0xC8FE
WINDOW_HI = 0xC8FF

# 씬 배치: (scene_lba, pool_base, text_bank0). 풀/복원 행은 전부 빌드 타임
# 상수 → 카드 엔트리에 완성 행 이미지(22B)로 수록, 로더는 복사만 한다.
# 뱅크 선정 근거 (2026-08-23 CDL 4세그: 대사·전투·지하도 + 메뉴):
#   전씬 공통 전뱅크 cold = $69/$6D/$6F/$7E 뿐 (메뉴가 $6C·$6E 소비 실측
#   — b7.1 장비 아이콘 깨짐 원인). 씬별 연속 3뱅크:
#   482-ctx cold ⊇ $7B/$7C/$7D, 290-ctx cold ⊇ $78/$79/$7A. 인덱스 = 공통 $7E.
# 2882: 조우+탑 병합 CDL(2026-08-23) — cold = $6D/$6F/$7E/$7F 뿐(비연속).
# → 행 구조를 씬당 4행(텍스트 뱅크 3개 개별 4섹터 + 인덱스 2섹터)으로 일반화.
# SCENES: (lba, pool_base, [텍스트 뱅크 3개 — 비연속 허용])
# 2882 재제외 (2026-08-23 밤): 탑 컨텍스트의 아이템 아이콘 read 는 소지
# 아이템에 의존 — 플레이 CDL 로 전수 불가 (b7.4 게이트에서 신규 획득 아이템
# 아이콘 깨짐 실측). 씬 확장 단계의 정적 자산 지도 도구로 재개.
SCENES = [(482, 9178, [0x7B, 0x7C, 0x7D]),
          (290, 9192, [0x78, 0x79, 0x7A])]
TEXT_SECTORS = 12                   # 디스크 상 텍스트 연속 12섹터 (4섹터×3뱅크)
INDEX_BANK = 0x7E
INDEX_SECTORS = 2
ROWS_IMG_LEN = 21                   # 4행×5B + FF (셋당)
ENTRY_LEN = 2 + ROWS_IMG_LEN * 2    # lba 2B + 풀 셋 + 복원 셋 = 44B
BANK_SIZE = 8192
INDEX_CAP = 0x780
ARMCHK = 0xA780
SCRATCH_KH = 0xAFFE
INDEX_MAGIC = bytes((0x42, 0xB4))
TRAP = bytes((0x00, 0xE7))

def scene_rows_image(lba: int, base: int, tbanks: list[int]) -> bytes:
    """씬의 SCRATCH 이미지 42B = 풀 4행+FF + 복원 4행+FF (전부 상수).
    텍스트는 뱅크당 4섹터 행 — 비연속 뱅크 지원."""
    def row(l, cnt, bank):
        return bytes(((l >> 16) & 0xFF, (l >> 8) & 0xFF, l & 0xFF, cnt, bank))
    img = bytearray()
    for i, b in enumerate(tbanks):
        img += row(base + i * 4, 4, b)
    img += row(base + TEXT_SECTORS, INDEX_SECTORS, INDEX_BANK)
    img.append(0xFF)
    for b in tbanks:
        img += row(lba + (b - 0x68) * 4, 4, b)
    img += row(lba + (INDEX_BANK - 0x68) * 4, INDEX_SECTORS, INDEX_BANK)
    img.append(0xFF)
    assert len(img) == ROWS_IMG_LEN * 2
    return bytes(img)

# 카드 테이블
CARD_TABLE_OFF = 0x3F054            # 카드 파일 오프셋 (무헤더)
CARD_BANK = 0x1F
CARD_TABLE_LOGICAL = 0xA000 + (CARD_TABLE_OFF - CARD_BANK * 0x2000)


# ---- 미니 어셈블러 (b6 계승) -------------------------------------------------

class Asm:
    def __init__(self, origin: int):
        self.origin = origin
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.buf)

    def label(self, name: str):
        self.labels[name] = self.pc

    def emit(self, *bs: int):
        self.buf.extend(bs)

    def branch(self, opcode: int, target: str):
        self.emit(opcode)
        self.fixups.append((len(self.buf), "rel", target))
        self.emit(0x00)

    def jsr(self, target):
        self._absop(0x20, target)

    def jmp(self, target):
        self._absop(0x4C, target)

    def _absop(self, op, target):
        self.emit(op)
        if isinstance(target, str):
            self.fixups.append((len(self.buf), "abs", target))
            self.emit(0x00, 0x00)
        else:
            self.emit(target & 0xFF, target >> 8)

    def resolve(self, external: dict[str, int] | None = None):
        table = {**(external or {}), **self.labels}
        for pos, kind, name in self.fixups:
            addr = table[name]
            if kind == "rel":
                delta = addr - (self.origin + pos + 1)
                if not -128 <= delta <= 127:
                    raise ValueError(f"branch out of range to {name}: {delta}")
                self.buf[pos] = delta & 0xFF
            else:
                self.buf[pos] = addr & 0xFF
                self.buf[pos + 1] = addr >> 8
        return bytes(self.buf)


def st_abs(a: Asm, addr: int):
    a.emit(0x8D, addr & 0xFF, addr >> 8)


def ld_abs(a: Asm, addr: int):
    a.emit(0xAD, addr & 0xFF, addr >> 8)


# ---- 로더 훅 v3 --------------------------------------------------------------

def asm_loader_v3() -> Asm:
    """v3.1 — 카드 테이블 엔트리 = [lba_mid, lba_lo, 행 이미지 22B] (24B).
    match: 22B 를 SCRATCH 로 복사(계산 코드 0) 후 원본 로드 + RUN(0, 풀 행).
    비매치+PRESENT=1: 직전 match 가 복사해 둔 복원 행으로 RUN(11)."""
    a = Asm(LOADER)
    a.emit(0xA5, 0xFF, 0xC9, 0x06)                 # LDA $FF CMP #$06
    a.branch(0xD0, "tail")                         # mode != 06 (직접 도달 가능 거리)
    # ---- 카드 테이블 걷기 (Y 는 블록 내 한정, carry 로 결과 전달) ----
    a.emit(0x5A)                                   # PHY
    a.emit(0x43, 0x20, 0x48)                       # TMA #$20 PHA
    a.emit(0xA9, CARD_BANK, 0x53, 0x20)            # 카드 매핑
    a.emit(0xC2)                                   # CLY
    a.label("loop")
    a.emit(0xB9, CARD_TABLE_LOGICAL & 0xFF, CARD_TABLE_LOGICAL >> 8)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "wnomatch")
    a.emit(0xC5, 0xFD)                             # CMP $FD (lba mid)
    a.branch(0xD0, "next")
    a.emit(0xB9, (CARD_TABLE_LOGICAL + 1) & 0xFF, (CARD_TABLE_LOGICAL + 1) >> 8)
    a.emit(0xC5, 0xFE)                             # CMP $FE (lba lo)
    a.branch(0xD0, "next")
    # match: 행 이미지 22B 를 SCRATCH 로 복사 (카드 매핑 상태에서)
    a.emit(0xDA)                                   # PHX
    a.emit(0xA2, 0x00)                             # LDX #0
    a.label("cpy")
    a.emit(0xB9, (CARD_TABLE_LOGICAL + 2) & 0xFF, (CARD_TABLE_LOGICAL + 2) >> 8)
    a.emit(0x9D, SCRATCH & 0xFF, SCRATCH >> 8)     # STA SCRATCH,X
    a.emit(0xC8, 0xE8, 0xE0, ROWS_IMG_LEN * 2)     # INY INX CPX #42
    a.branch(0xD0, "cpy")
    a.emit(0xFA)                                   # PLX
    a.emit(0x68, 0x53, 0x20, 0x7A)                 # PLA TAM#$20 PLY
    a.emit(0x38)                                   # SEC = match
    a.branch(0x80, "walked")
    a.label("next")
    a.emit(0x98, 0x18, 0x69, ENTRY_LEN, 0xA8)      # TYA CLC ADC #44 TAY
    a.branch(0x80, "loop")
    a.label("wnomatch")
    a.emit(0x68, 0x53, 0x20, 0x7A)                 # PLA TAM#$20 PLY
    a.emit(0x18)                                   # CLC = nomatch
    a.label("walked")
    a.branch(0xB0, "match")
    # ---- 비매치: PRESENT=1 → 복사돼 있는 복원 행으로 RUN ----
    ld_abs(a, PRESENT)
    a.branch(0xF0, "tail")
    a.emit(0xA9, RESTORE_OFF)
    a.jsr("run")
    a.emit(0x9C, PRESENT & 0xFF, PRESENT >> 8)     # STZ PRESENT
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.label("tail")
    a.emit(0x4C, 0x09, 0xE0)                       # JMP $E009
    # ---- match: 씬 로드 + 풀 적재 ----
    a.label("match")
    a.emit(0x20, 0x09, 0xE0)                       # JSR $E009 원본 로드
    a.emit(0x08, 0x48)                             # PHP PHA
    a.emit(0xA9, 0x00)
    a.jsr("run")
    a.emit(0xA9, 0x01)
    st_abs(a, PRESENT)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.emit(0x68, 0x28, 0x60)                       # PLA PLP RTS
    # ---- RUN (테이블 = SCRATCH + A오프셋, zp $F8-$FF 보존 = $20F8 절대 루프) ----
    a.label("run")
    a.emit(0x08, 0x48, 0xDA, 0x5A)                 # PHP PHA PHX PHY
    a.emit(0xAA)                                   # TAX (테이블 오프셋)
    a.emit(0xA0, 0x00)                             # LDY #0
    a.label("zsave")
    a.emit(0xB9, 0xF8, 0x20)                       # LDA $20F8,Y (zp 절대 접근)
    a.emit(0x48)                                   # PHA
    a.emit(0xC8, 0xC0, 0x08)                       # INY CPY #8
    a.branch(0xD0, "zsave")
    a.label("rloop")
    a.emit(0xBD, SCRATCH & 0xFF, SCRATCH >> 8)     # LDA SCRATCH,X
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "endrun")
    a.emit(0x85, 0xFC)
    for off, zp in ((1, 0xFD), (2, 0xFE), (3, 0xF8), (4, 0xFA)):
        a.emit(0xBD, (SCRATCH + off) & 0xFF, (SCRATCH + off) >> 8)
        a.emit(0x85, zp)
    a.emit(0x64, 0xF9, 0x64, 0xFB)                 # STZ $F9 STZ $FB
    a.emit(0xA9, 0x06, 0x85, 0xFF)                 # LDA #$06 STA $FF
    a.emit(0xDA, 0x20, 0x09, 0xE0, 0xFA)           # PHX JSR $E009 PLX
    a.emit(0x8A, 0x18, 0x69, 0x05, 0xAA)           # TXA CLC ADC #5 TAX
    a.branch(0x80, "rloop")
    a.label("endrun")
    a.emit(0xA0, 0x07)                             # LDY #7 — 역순 복원
    a.label("zrest")
    a.emit(0x68)                                   # PLA
    a.emit(0x99, 0xF8, 0x20)                       # STA $20F8,Y
    a.emit(0x88)                                   # DEY
    a.branch(0x10, "zrest")                        # BPL
    a.emit(0x7A, 0xFA, 0x68, 0x28)                 # PLY PLX PLA PLP
    a.emit(0x60)
    return a


# ---- 이설 슬라이스 / 리더 / 뱅크81 (b6 그대로) --------------------------------

def make_slice(src: bytes) -> bytes:
    body = bytearray(src)
    j = SLICE_JSR_E009 - SLICE_LO
    assert body[j:j + 3] == bytes((0x20, 0x09, 0xE0))
    body[j + 1] = LOADER & 0xFF
    body[j + 2] = LOADER >> 8
    body.append(0x60)
    return bytes(body)


def asm_reader(origin: int) -> Asm:
    a = Asm(origin)
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)
    a.emit(0xA9, INDEX_BANK, 0x53, 0x20)
    a.jsr(ARMCHK)
    a.emit(0x68, 0x53, 0x20)
    a.branch(0xB0, "native")
    a.label("serve")
    a.emit(0x43, 0x20, 0x48)
    a.emit(0xAD, TBANK & 0xFF, TBANK >> 8, 0x53, 0x20)
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x85, 0x00)
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x85, 0x01)
    a.emit(0xB2, 0x00)
    a.branch(0xF0, "nul")
    a.emit(0x8D, 0x80, 0x2D)
    a.emit(0xEE, CURL & 0xFF, CURL >> 8)
    a.branch(0xD0, "nohi")
    a.emit(0xEE, CURH & 0xFF, CURH >> 8)
    a.label("nohi")
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x18, 0x60)
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.label("native")
    a.emit(0x38, 0x60)
    return a


def asm_bank81(wnd_slice: int, wnd_reader: int) -> bytes:
    a = Asm(SLICE_LO)
    a.jsr(wnd_slice)
    a.emit(0x80, 0x25)                             # BRA $6704
    assert a.pc == TRAMP
    a.emit(0x43, 0x40, 0x48)
    a.emit(0xA9, 0x84, 0x53, 0x40)
    a.jsr(wnd_reader)
    a.emit(0x68, 0x53, 0x40)
    a.branch(0xB0, "tonat")
    a.emit(0xAD, 0x80, 0x2D)
    a.emit(0x60)
    a.label("tonat")
    a.emit(0x4C, 0x84, 0x42)
    code = a.resolve()
    assert len(code) <= SLICE_HI - SLICE_LO
    return code + b"\xFF" * (SLICE_HI - SLICE_LO - len(code))


def asm_armchk() -> bytes:
    a = Asm(ARMCHK)
    a.emit(0xDA, 0x5A)
    a.emit(0xA5, 0x53)
    a.branch(0xD0, "p0")
    a.emit(0xAD, 0x69, 0x2E)
    a.branch(0xD0, "p0")
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
    a.emit(0xAA)
    a.emit(0xAD, 0x00, 0xA0, 0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "p0")
    a.emit(0xAD, 0x01, 0xA0, 0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "p0")
    a.branch(0x80, "cont")
    a.label("p0")
    a.jmp("pass")
    a.label("cont")
    a.emit(0xA5, 0x4C, 0x29, 0x1F)
    a.emit(0x8D, SCRATCH_KH & 0xFF, SCRATCH_KH >> 8)
    a.emit(0x8A, 0x0A, 0xAA)
    a.emit(0xBD, 0x02, 0xA0, 0x85, 0x00)
    a.emit(0xBD, 0x03, 0xA0, 0x85, 0x01)
    a.label("loop")
    a.emit(0xA0, 0x00)
    a.emit(0xB1, 0x00)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "pass")
    a.emit(0xCD, SCRATCH_KH & 0xFF, SCRATCH_KH >> 8)
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
    a.emit(0xB1, 0x00, 0x8D, TBANK & 0xFF, TBANK >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, CURL & 0xFF, CURL >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, CURH & 0xFF, CURH >> 8)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x65, 0x4C, 0x85, 0x4C)
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)
    a.emit(0x7A, 0xFA)
    a.emit(0x18, 0x60)
    a.label("pass")
    a.emit(0x7A, 0xFA)
    a.emit(0x38, 0x60)
    return a.resolve()


# ---- 씬별 풀 패킹 -------------------------------------------------------------

def pack_scene(records, armchk: bytes, text_banks: list[int]):
    banks = {b: bytearray() for b in text_banks}
    placed = {}
    for r in sorted(records, key=lambda r: -r["encoded_length"]):
        data = bytes.fromhex(r["encoded_hex"])
        if 0 in data[:-1]:
            raise ValueError(f"{r['id']}: 내부 00")
        for b in text_banks:
            if len(banks[b]) + len(data) <= BANK_SIZE:
                placed[r["id"]] = (b, len(banks[b]))
                banks[b].extend(data)
                break
        else:
            raise ValueError(f"{r['id']}: 텍스트 뱅크 부족")

    buckets = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, boff = placed[r["id"]]
        buckets[kb].append(((off13 >> 8) & 0x1F, off13 & 0xFF, bank,
                            0xA000 + boff, r["original_raw_length"]))
    entry_area = bytearray()
    ptrs = []
    base = 0xA000 + 2 + 24 * 2
    for kb in range(24):
        ptrs.append(base + len(entry_area))
        for oh, ol, bank, addr, ln in sorted(buckets[kb]):
            lm1 = ln - 1
            entry_area.extend((oh, ol, bank, addr & 0xFF, addr >> 8,
                               lm1 & 0xFF, lm1 >> 8))
        entry_area.append(0xFF)
    index = bytearray(INDEX_MAGIC)
    for p in ptrs:
        index.extend((p & 0xFF, p >> 8))
    index.extend(entry_area)
    if len(index) > INDEX_CAP:
        raise ValueError(f"인덱스 {len(index)}B > {INDEX_CAP:#x}")

    # 텍스트 12섹터 이미지 (뱅크별 8192 정렬, 잔여 트랩)
    text_img = bytearray()
    for i, b in enumerate(text_banks):
        seg = bytearray(banks[b])
        while len(seg) < BANK_SIZE:
            seg.extend(TRAP)
        text_img.extend(seg[:BANK_SIZE])
    # 인덱스 2섹터 이미지 (인덱스 + armchk + 트랩)
    idx_img = bytearray(index)
    idx_img.extend(b"\x00" * (INDEX_CAP - len(index)))
    idx_img.extend(armchk)
    assert INDEX_CAP + len(armchk) <= 0xFFE
    while len(idx_img) < INDEX_SECTORS * 2048:
        idx_img.extend(TRAP)
    return bytes(text_img), bytes(idx_img[:INDEX_SECTORS * 2048]), \
        {f"{b:02X}": len(banks[b]) for b in text_banks}, len(index)


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 사전검증
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42))
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65))
    assert slice_src[-2:] == bytes((0xD0, 0xD6))
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창 오염"
    assert len(SCENES) * ENTRY_LEN <= 240, "카드 테이블 Y 인덱스(8bit) 한계 — 분할 필요"
    for lba, base, tbanks in SCENES:
        assert lba < 0x10000 and base < 0x10000 and len(tbanks) == 3
        seg = bytes(out[T2 + base * 2048: T2 + (base + 14) * 2048])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"

    # 창 조립
    loader = asm_loader_v3().resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > WINDOW_CODE_END:
        raise ValueError(f"창 코드 초과: {wnd_end:#06x} > {WINDOW_CODE_END:#06x}")
    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)
    armchk = asm_armchk()

    # 씬별 페이로드 → 풀 이미지
    scene_stats = {}
    pool_patches = []
    for lba, base, tbanks in SCENES:
        pl = json.loads((ROOT / "translation" /
                         (f"btrack_b7_scene_{lba}_payload.json"
                          if lba != 482 else "btrack_b4_field_payload.json")
                         ).read_text(encoding="utf-8"))["records"]
        text_img, idx_img, tstats, ilen = pack_scene(pl, armchk, tbanks)
        pool_patches.append((T2 + base * 2048, text_img, f"scene {lba} text"))
        pool_patches.append((T2 + (base + TEXT_SECTORS) * 2048, idx_img,
                             f"scene {lba} index"))
        scene_stats[str(lba)] = {"records": len(pl), "text": tstats,
                                 "index_bytes": ilen, "pool_base": base,
                                 "text_banks": [f"{b:02X}" for b in tbanks]}

    # 패치 적용 (SCRATCH 는 매치 시 카드에서 복사되므로 사전 구움 불필요)
    patches = [(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8)), "vector"),
               (eng_off(SLICE_LO), bank81, "bank81"),
               (eng_off(WINDOW_LO), loader + wslice + reader, "window code"),
               (eng_off(FLAG), bytes(6), "state=0")] + pool_patches
    for off, data, _ in patches:
        out[off:off + len(data)] = data
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(SRC_CUE.read_text(encoding="ascii")
                       .replace("Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin",
                                OUT_BIN.name), encoding="ascii")

    # 카드: btrack_full + 씬 테이블
    card = bytearray(CARD_SRC.read_bytes())
    table = bytearray()
    for lba, base, tbanks in SCENES:
        table.extend(((lba >> 8) & 0xFF, lba & 0xFF))
        table.extend(scene_rows_image(lba, base, tbanks))
    table.append(0xFF)
    # 종결 FF 가 lba_mid 로 오인될 일 없음: mid=FF ⇒ lba ≥ 0xFF00 > 트랙 섹터수
    assert set(card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)]) == {0xFF}, \
        "카드 테이블 자리 FF 아님"
    card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)] = table
    CARD_OUT.write_bytes(bytes(card))

    # 디스어셈블 검산 (창 로더)
    r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{LOADER:X}",
                        f"{eng_off(LOADER):X}", f"{len(loader):X}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"loader disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B7-HOOK-BUILD",
        "runtime_status": "PENDING",
        "scenes": scene_stats,
        "card": {"out": CARD_OUT.name, "table_off": hex(CARD_TABLE_OFF),
                 "table_logical": hex(CARD_TABLE_LOGICAL),
                 "entries": len(SCENES)},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader),
                   "free": WINDOW_CODE_END - wnd_end},
        "output_bin_sha256": sha256(out),
        "card_sha256": sha256(card),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK",
                      "window": manifest["window"],
                      "scenes": {k: v["records"] for k, v in scene_stats.items()},
                      "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "sha256": manifest["output_bin_sha256"][:16]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
