#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B5 — 리더 훅 재배치 재빌드 (2026-08-23 설계, V18 검증 사항 계승).

b4 대비 핵심 변경 (근거: docs/HANDOFF.md §1·§6, 2026-08-23 세션):
  - regions A/B/state($4F12../$4C50../$4F9B..) **미사용** — 라이브 엔진 코드로 판명.
  - 풀 디스크 위치 = LBA 9178(16K $7A/$7B)/9186(8K $7E)/9190(4K $6D전반)
    — V18 런타임 검증 PASS. 5480..5493 은 전투 자산이므로 불변.
  - 상주부 최소화: 로더 슬라이스($66DA..$6703, 42B)를 FF 창으로 이설해 뱅크 $81
    에 37B 확보 → 리더 트램펄린 22B 배치. 트램펄린이 MPR6=$84 를 브래킷하므로
    리더 본체는 FF 창에 산다. (MPR 보편성 실측: $4036 호출 시 MPR2=$80·MPR3=$81
    만 100%, MPR4~6 가변 — ziria_z6_stream_source_trace.tsv 10,559건)
  - armchk/match 는 풀 bank $6D 의 인덱스 뒤(고정 $A780)에 탑재, 디스패처가
    MPR5=$6D 브래킷 후 JSR. 상태(FLAG/TBANK/CURL/CURH/PRESENT)는 창 끝.

배치 요약:
  bank $81: $66DA JSR wnd_slice + BRA $6704, $66DF 트램펄린(22B), 잔여 FF
  vector  : $4036 JMP $4284 -> JMP tramp (operand 2B)
  FF 창   : loader hook v2($C737) + 이설 슬라이스 + 리더 디스패치/serve + 상태
  pool $6D: magic+인덱스(cap 0x780) + armchk/match($A780) + 스크래치($AFFE)

입력: 원본 BIN + translation/btrack_b4_field_payload.json (레코드 불변)
출력: Tenshi..._btrack_b5_field.bin/.cue + manifest
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
PAYLOAD = ROOT / "translation" / "btrack_b4_field_payload.json"
DISASM = ROOT / "tools" / "huc6280_disasm_verifier" / "bin" / "Debug" / "net8.0" / "huc6280_disasm_verifier.exe"

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b5_field"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "btrack_b5_hook_manifest.json"

T2 = 7_914_480
ENGINE_LBA = 258
ENG = T2 + ENGINE_LBA * 2048


def eng_off(logical: int) -> int:
    """엔진 상주 매핑(MPR2..6 = $80..$84) 기준 logical -> 디스크 오프셋."""
    assert 0x4000 <= logical < 0xE000
    return ENG + (logical - 0x4000)


# ---- 배치 상수 ---------------------------------------------------------------

VECTOR = 0x4036                     # JMP $4284 -> JMP TRAMP (operand만)
SLICE_LO, SLICE_HI = 0x66DA, 0x6704  # [lo, hi) 이설 슬라이스 42B
SLICE_JSR_E009 = 0x66FC             # 슬라이스 내부의 JSR $E009 위치
TRAMP = 0x66DF                      # 트램펄린 (JSR+BRA 5B 뒤)

WINDOW_LO, WINDOW_HI = 0xC737, 0xC8FF  # 원본 FF 창 (PRESENT 포함 끝 $C8FE)
LOADER = 0xC737

# 상태 (창 끝)
FLAG, TBANK, CURL, CURH = 0xC8F9, 0xC8FA, 0xC8FB, 0xC8FC
PRESENT = 0xC8FE
STATE_LO = 0xC8F9

# 풀 디스크 배치 (V18 검증 PASS)
POOL_ROWS = [(9178, 8, 0x7A), (9186, 4, 0x7E), (9190, 2, 0x6D)]
RESTORE_ROWS = [(554, 8, 0x7A), (570, 4, 0x7E), (502, 2, 0x6D)]
TEXT_BANKS = [0x7A, 0x7B, 0x7E]
BANK_SIZE = 8192
INDEX_BANK = 0x6D
INDEX_CAP = 0x780                   # 인덱스 상한 — 이후 armchk 코드
ARMCHK = 0xA780                     # $6D 매핑(MPR5) 기준 armchk 진입
SCRATCH_KH = 0xAFFE                 # $6D 내 스크래치
POOL_6D_BYTES = 4096                # 2섹터
INDEX_MAGIC = bytes((0x42, 0xB4))
TRAP = bytes((0x00, 0xE7))


# ---- 미니 어셈블러 (b4 계승) -------------------------------------------------

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


# ---- 창 코드: loader hook v2 (V18 사양) --------------------------------------

def asm_loader_hook() -> Asm:
    """482 로드 시 풀 적재+PRESENT=1, 그 외 mode-06 로드 직전 복원+PRESENT=0.
    V18 과 동일 로직. FLAG/PRESENT 는 창 상태 바이트."""
    a = Asm(LOADER)
    a.emit(0xA5, 0xFF, 0xC9, 0x06)                 # LDA $FF CMP #$06
    a.branch(0xD0, "tail")
    a.emit(0xA5, 0xFC)
    a.branch(0xD0, "notf")
    a.emit(0xA5, 0xFD, 0xC9, 0x01)
    a.branch(0xD0, "notf")
    a.emit(0xA5, 0xFE, 0xC9, 0xE2)
    a.branch(0xD0, "notf")
    a.emit(0xA5, 0xF8, 0xC9, 0x60)
    a.branch(0xD0, "notf")
    # --- field 482/96 ---
    a.emit(0x20, 0x09, 0xE0)                       # JSR $E009 (원본 로드)
    a.emit(0x08, 0x48)                             # PHP PHA
    a.emit(0xA9, 0x00)                             # A = 풀 테이블 오프셋
    a.jsr("run")
    a.emit(0xA9, 0x01, 0x8D, PRESENT & 0xFF, PRESENT >> 8)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)           # STZ FLAG
    a.emit(0x68, 0x28)                             # PLA PLP
    a.emit(0x60)                                   # RTS
    a.label("notf")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "tail")
    a.emit(0xA9, 0x10)                             # A = 복원 테이블 오프셋
    a.jsr("run")
    a.emit(0x9C, PRESENT & 0xFF, PRESENT >> 8)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.label("tail")
    a.emit(0x4C, 0x09, 0xE0)                       # JMP $E009
    # --- RUN ---
    a.label("run")
    a.emit(0x08, 0x48, 0xDA, 0x5A)                 # PHP PHA PHX PHY
    a.emit(0xAA)                                   # TAX
    for zp in range(0xF8, 0x100):
        a.emit(0xA5, zp, 0x48)                     # LDA zp PHA
    a.label("loop")
    a.emit(0xBD, 0x00, 0x00)
    a.fixups.append((len(a.buf) - 2, "abs", "tbl"))
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "endrun")
    a.emit(0x85, 0xFC)
    for off, zp in ((1, 0xFD), (2, 0xFE), (3, 0xF8), (4, 0xFA)):
        a.emit(0xBD, 0x00, 0x00)
        a.fixups.append((len(a.buf) - 2, "abs+%d" % off, "tbl"))
        a.emit(0x85, zp)
    a.emit(0x64, 0xF9, 0x64, 0xFB)                 # STZ $F9 STZ $FB
    a.emit(0xA9, 0x06, 0x85, 0xFF)                 # LDA #$06 STA $FF
    a.emit(0xDA, 0x20, 0x09, 0xE0, 0xFA)           # PHX JSR $E009 PLX
    a.emit(0x8A, 0x18, 0x69, 0x05, 0xAA)           # TXA CLC ADC #$05 TAX
    a.branch(0x80, "loop")
    a.label("endrun")
    for zp in range(0xFF, 0xF7, -1):
        a.emit(0x68, 0x85, zp)                     # PLA STA zp
    a.emit(0x7A, 0xFA, 0x68, 0x28)                 # PLY PLX PLA PLP
    a.emit(0x60)                                   # RTS
    a.label("tbl")
    for lba, cnt, bank in POOL_ROWS:
        a.emit((lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF, cnt, bank)
    a.emit(0xFF)
    for lba, cnt, bank in RESTORE_ROWS:
        a.emit((lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF, cnt, bank)
    a.emit(0xFF)
    # abs+N 해석
    for pos, kind, name in list(a.fixups):
        if kind.startswith("abs+"):
            delta = int(kind[4:])
            addr = a.labels[name] + delta
            a.buf[pos] = addr & 0xFF
            a.buf[pos + 1] = addr >> 8
            a.fixups.remove((pos, kind, name))
    return a


# ---- 창 코드: 이설 슬라이스 --------------------------------------------------

def make_slice(src: bytes, origin: int) -> bytes:
    """$66DA..$6703 원본 42B 를 창으로 이설. JSR $E009 -> JSR LOADER,
    내부 상대분기(재시도 BNE)는 통째 이동이라 무변. 끝에 RTS."""
    body = bytearray(src)
    j = SLICE_JSR_E009 - SLICE_LO
    assert body[j:j + 3] == bytes((0x20, 0x09, 0xE0)), "슬라이스 JSR $E009 불일치"
    body[j + 1] = LOADER & 0xFF
    body[j + 2] = LOADER >> 8
    body.append(0x60)                              # RTS
    return bytes(body)


# ---- 창 코드: 리더 디스패치 + serve ------------------------------------------

def asm_reader(origin: int) -> Asm:
    a = Asm(origin)
    a.emit(0xA5, 0x55)                             # LDA $55 — native 우선
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)                       # TMA #$20 PHA
    a.emit(0xA9, INDEX_BANK, 0x53, 0x20)           # LDA #$6D TAM #$20
    a.jsr(ARMCHK)
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.branch(0xB0, "native")                       # BCS — 미채택
    a.label("serve")
    a.emit(0x43, 0x20, 0x48)                       # TMA #$20 PHA
    a.emit(0xAD, TBANK & 0xFF, TBANK >> 8, 0x53, 0x20)
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x85, 0x00)
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x85, 0x01)
    a.emit(0xB2, 0x00)                             # LDA ($00)
    a.branch(0xF0, "nul")
    a.emit(0x8D, 0x80, 0x2D)                       # STA $2D80
    a.emit(0xEE, CURL & 0xFF, CURL >> 8)
    a.branch(0xD0, "nohi")
    a.emit(0xEE, CURH & 0xFF, CURH >> 8)
    a.label("nohi")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x18, 0x60)                             # CLC RTS — tramp 가 $2D80 반환
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)           # STZ FLAG
    a.label("native")
    a.emit(0x38, 0x60)                             # SEC RTS — tramp 가 $4284 로
    return a


# ---- 뱅크 $81: 슬라이스 대체 + 트램펄린 --------------------------------------

def asm_bank81(wnd_slice: int, wnd_reader: int) -> bytes:
    a = Asm(SLICE_LO)
    a.jsr(wnd_slice)                               # 이설 슬라이스 호출
    a.emit(0x80, 0x25)                             # BRA $6704 (=$66DF+0x25)
    assert a.pc == TRAMP
    a.emit(0x43, 0x40, 0x48)                       # TMA #$40 PHA
    a.emit(0xA9, 0x84, 0x53, 0x40)                 # LDA #$84 TAM #$40
    a.jsr(wnd_reader)
    a.emit(0x68, 0x53, 0x40)                       # PLA TAM #$40 (carry 보존)
    a.branch(0xB0, "tonat")                        # BCS
    a.emit(0xAD, 0x80, 0x2D)                       # LDA $2D80
    a.emit(0x60)                                   # RTS
    a.label("tonat")
    a.emit(0x4C, 0x84, 0x42)                       # JMP $4284
    code = a.resolve()
    assert len(code) <= SLICE_HI - SLICE_LO, f"bank81 {len(code)}B > 42B"
    return code + b"\xFF" * (SLICE_HI - SLICE_LO - len(code))


# ---- 풀 $6D: armchk + match --------------------------------------------------

def asm_armchk() -> bytes:
    a = Asm(ARMCHK)
    a.emit(0xDA, 0x5A)                             # PHX PHY
    a.emit(0xA5, 0x53)
    a.branch(0xD0, "p0")
    a.emit(0xAD, 0x69, 0x2E)                       # LDA $2E69
    a.branch(0xD0, "p0")
    a.emit(0xA5, 0x4C, 0xC9, 0x80)
    a.branch(0x90, "p0")
    a.emit(0xC9, 0xE0)
    a.branch(0xB0, "p0")
    a.emit(0x4A, 0x4A, 0x4A, 0x4A, 0x4A)           # LSR x5
    a.emit(0x18, 0x69, 0x08)                       # CLC ADC #$08
    a.emit(0x6D, 0xD0, 0x22)                       # ADC $22D0
    a.emit(0x38, 0xE9, 0x68)                       # SEC SBC #$68
    a.emit(0xC9, 0x18)
    a.branch(0xB0, "p0")                           # rel >= 24
    a.emit(0xAA)                                   # TAX (rel bank)
    a.emit(0xAD, 0x00, 0xA0, 0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "p0")
    a.emit(0xAD, 0x01, 0xA0, 0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "p0")
    a.branch(0x80, "cont")                         # BRA cont
    a.label("p0")
    a.jmp("pass")                                  # 원거리 pass 중계
    a.label("cont")
    a.emit(0xA5, 0x4C, 0x29, 0x1F)                 # LDA $4C AND #$1F
    a.emit(0x8D, SCRATCH_KH & 0xFF, SCRATCH_KH >> 8)
    a.emit(0x8A, 0x0A, 0xAA)                       # TXA ASL TAX
    a.emit(0xBD, 0x02, 0xA0, 0x85, 0x00)           # bucket ptr lo
    a.emit(0xBD, 0x03, 0xA0, 0x85, 0x01)           # bucket ptr hi
    a.label("loop")
    a.emit(0xA0, 0x00)                             # LDY #0
    a.emit(0xB1, 0x00)                             # LDA ($00),Y  off_hi
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "pass")
    a.emit(0xCD, SCRATCH_KH & 0xFF, SCRATCH_KH >> 8)
    a.branch(0xD0, "next")
    a.emit(0xC8, 0xB1, 0x00)                       # INY LDA ($00),Y  off_lo
    a.emit(0xC5, 0x4B)
    a.branch(0xF0, "match")
    a.label("next")
    a.emit(0x18, 0xA5, 0x00, 0x69, 0x07, 0x85, 0x00)
    a.branch(0x90, "loop")
    a.emit(0xE6, 0x01)
    a.branch(0x80, "loop")
    a.label("match")
    a.emit(0xA0, 0x02)                             # LDY #2
    a.emit(0xB1, 0x00, 0x8D, TBANK & 0xFF, TBANK >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, CURL & 0xFF, CURL >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x8D, CURH & 0xFF, CURH >> 8)
    a.emit(0xC8, 0xB1, 0x00)                       # (len-1) lo
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)
    a.emit(0xC8, 0xB1, 0x00)                       # (len-1) hi
    a.emit(0x65, 0x4C, 0x85, 0x4C)
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.emit(0x18, 0x60)                             # CLC RTS — 채택
    a.label("pass")
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.emit(0x38, 0x60)                             # SEC RTS — 원본 경로
    return a.resolve()


# ---- 인덱스·풀 패킹 (b4 계승, 인덱스 캡 0x780) --------------------------------

def pack_pool(records):
    banks = {b: bytearray() for b in TEXT_BANKS}
    placed = {}
    for r in sorted(records, key=lambda r: -r["encoded_length"]):
        data = bytes.fromhex(r["encoded_hex"])
        if 0 in data[:-1]:
            raise ValueError(f"{r['id']}: 내부 00 바이트")
        for b in TEXT_BANKS:
            if len(banks[b]) + len(data) <= BANK_SIZE:
                placed[r["id"]] = (b, len(banks[b]))
                banks[b].extend(data)
                break
        else:
            raise ValueError(f"{r['id']}: 텍스트 뱅크 공간 부족")

    buckets = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, boff = placed[r["id"]]
        buckets[kb].append((
            (off13 >> 8) & 0x1F, off13 & 0xFF, bank,
            0xA000 + boff, r["original_raw_length"]))

    entry_area = bytearray()
    bucket_ptrs = []
    base = 0xA000 + 2 + 24 * 2
    for kb in range(24):
        bucket_ptrs.append(base + len(entry_area))
        for off_hi, off_lo, bank, addr, ln in sorted(buckets[kb]):
            lm1 = ln - 1
            entry_area.extend((off_hi, off_lo, bank,
                               addr & 0xFF, addr >> 8, lm1 & 0xFF, lm1 >> 8))
        entry_area.append(0xFF)
    index = bytearray(INDEX_MAGIC)
    for p in bucket_ptrs:
        index.extend((p & 0xFF, p >> 8))
    index.extend(entry_area)
    if len(index) > INDEX_CAP:
        raise ValueError(f"인덱스 {len(index)}B > {INDEX_CAP:#x}")
    return banks, bytes(index), placed


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # ---- 사전검증: 원본 바이트 확인 ----
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42)), \
        "$4036 벡터 원본 불일치"
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65)), "슬라이스 시작 불일치(PHX LDA $6531,X)"
    assert slice_src[-2:] == bytes((0xD0, 0xD6)), "슬라이스 끝 불일치(BNE -42)"
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창이 순수 FF 아님"
    for lba, cnt, _ in POOL_ROWS:
        seg = bytes(out[T2 + lba * 2048: T2 + (lba + cnt) * 2048])
        assert set(seg) == {0}, f"풀 대상 LBA {lba} 원본이 00-fill 아님"

    # ---- 창 레이아웃 조립 ----
    loader_asm = asm_loader_hook()
    loader = loader_asm.resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src, wnd_slice_addr)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > STATE_LO:
        raise ValueError(f"창 예산 초과: 코드 끝 {wnd_end:#06x} > 상태 {STATE_LO:#06x}")

    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)

    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    records = payload["records"]
    banks, index, placed = pack_pool(records)
    armchk = asm_armchk()
    pool_6d = bytearray(index)
    pool_6d.extend(b"\x00" * (INDEX_CAP - len(index)))
    pool_6d.extend(armchk)
    assert INDEX_CAP + len(armchk) <= 0xFFE, "armchk 가 스크래치 침범"
    while len(pool_6d) < POOL_6D_BYTES:
        pool_6d.extend(TRAP)
    pool_6d = pool_6d[:POOL_6D_BYTES]

    # ---- 패치 적용 ----
    patches = []

    def patch(off, data, why):
        patches.append((off, bytes(data), why))

    patch(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8)),
          "$4036 vector operand -> tramp")
    patch(eng_off(SLICE_LO), bank81, "bank81 slice-out + tramp")
    wnd = loader + wslice + reader
    patch(eng_off(WINDOW_LO), wnd, "window: loader+slice+reader")
    patch(eng_off(STATE_LO), bytes(6), "state FLAG/TBANK/CURL/CURH/spare/PRESENT=0")
    for lba, cnt, bank in POOL_ROWS:
        if bank == INDEX_BANK:
            blob = bytes(pool_6d)
        elif cnt == 4:
            blob = bytes(banks[bank])
        else:
            a7 = bytearray(banks[0x7A])            # $7B 는 섹터 경계(8192) 정렬 필수
            while len(a7) < BANK_SIZE:
                a7.extend(TRAP)
            blob = bytes(a7[:BANK_SIZE]) + bytes(banks[0x7B])
        cap = cnt * 2048
        pad = bytearray()
        while len(blob) + len(pad) < cap:
            pad.extend(TRAP)
        patch(T2 + lba * 2048, (blob + bytes(pad))[:cap], f"pool @LBA {lba} bank {bank:02X}")

    original_hex = {}
    for off, data, why in patches:
        original_hex[why] = bytes(out[off:off + len(data)]).hex().upper()[:96]
        out[off:off + len(data)] = data

    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(SRC_CUE.read_text(encoding="ascii")
                       .replace("Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin",
                                OUT_BIN.name), encoding="ascii")

    # ---- 디스어셈블 검산 ----
    disasm = {}
    checks = [
        ("bank81", SLICE_LO, eng_off(SLICE_LO), len(bank81) - bank81.count(0xFF) + 0),
        ("window", WINDOW_LO, eng_off(WINDOW_LO), len(wnd)),
    ]
    for name, logical, off, ln in checks:
        if name == "bank81":
            ln = 27  # JSR+BRA(5) + tramp(22)
        r = subprocess.run(
            [str(DISASM), "--raw", str(OUT_BIN), f"{logical:X}", f"{off:X}", f"{ln:X}"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")
        disasm[name] = r.stdout.strip().splitlines()

    manifest = {
        "format": "BTRACK-B5-FIELD-HOOK-BUILD",
        "runtime_status": "PENDING",
        "design": "리더 재배치: regions A/B 미사용, 슬라이스 이설+트램펄린, armchk in $6D, pool @9178 (HANDOFF §1 2026-08-23)",
        "layout": {
            "vector": f"$4036 -> JMP ${TRAMP:04X}",
            "bank81_tramp": f"${TRAMP:04X} (22B)",
            "window": {
                "loader": f"${LOADER:04X} ({len(loader)}B)",
                "slice": f"${wnd_slice_addr:04X} ({len(wslice)}B)",
                "reader": f"${wnd_reader_addr:04X} ({len(reader)}B)",
                "state": f"${STATE_LO:04X}..${PRESENT:04X}",
                "free": STATE_LO - wnd_end,
            },
            "pool_6d": {"index": len(index), "armchk": len(armchk),
                        "armchk_at": f"${ARMCHK:04X}"},
        },
        "pool": {
            "rows": [f"LBA {l} x{c} -> {b:02X}" for l, c, b in POOL_ROWS],
            "text_bytes": {f"{b:02X}": len(banks[b]) for b in TEXT_BANKS},
            "records": len(records),
        },
        "original_bytes_replaced": original_hex,
        "disasm": disasm,
        "runtime_gate": [
            "첫 필드 첫 대사 전면 한글",
            "필드 전투 5~10회 + 맵 이동 + 탑 이벤트 전투 (강화 게이트)",
            "Memo·초상화·NPC·건물 회귀, EXEC BRK·멈춤·깨짐 0",
            "BGM 전곡 정상",
        ],
        "output_bin_sha256": sha256(out),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({
        "status": "BUILD_OK",
        "window_bytes": {"loader": len(loader), "slice": len(wslice),
                         "reader": len(reader), "free": STATE_LO - wnd_end},
        "pool_6d": {"index": len(index), "armchk": len(armchk)},
        "bin": OUT_BIN.name,
        "sha256": manifest["output_bin_sha256"][:16],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
