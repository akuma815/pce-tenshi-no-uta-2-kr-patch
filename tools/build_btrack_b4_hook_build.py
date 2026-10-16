#!/usr/bin/env python3
"""B트랙 B4 — reader redirect 훅 + 번역 풀 통합 빌드.

설계 (2026-08-22 디스어셈블 실측 기반):
  - `$4036: JMP $4284` 벡터를 새 디스패치로 교체. 직접 `$4284` 호출자는 0건 실측.
  - 디스패치: FLAG 활성 시 번역 스트림 서비스(SERVE), 비활성 시 레코드 시작
    검사(ARMCHK) 후 원본 `$4284` 로 통과.
  - ARMCHK: 기본 스트림 전용 가드($55/$53/$2E69 == 0), `$4C∈[80,E0)`,
    bank = $22D0 + 0x0C + (hi>>5) - 4, rel = bank-$68 (<24).
    bank $6D 인덱스를 MPR5 브래킷으로 조회. 일치 시:
    $54/$55 = 번역 주소($A000 창), TBANK 설정, `$4B/$4C += len-1`
    (원문 terminator 00 위치), FLAG=1, 첫 바이트 즉시 SERVE.
  - SERVE: MPR5=TBANK 브래킷 후 `LDA ($54)`. 00 이면 FLAG·$54/$55 정리 후
    `JMP $4284` — 기본 스트림이 원문 00을 반환해 종료 의미와 바이트코드
    재개 위치(P+len)를 원본과 동일하게 보존한다 (native ptr54 NUL 관용구).
  - 코드 배치는 3-세그먼트 CDL 무접근 실측 구간(bank $80 내):
    A `$4F12..$4FA1`(dispatch+serve+state), B `$4C50..$4CD2`(armchk),
    C `$5184..$5230`(match). canary 로더 훅($C737)·callsite($66FC)와 비충돌.
  - 풀(캐너리 PASS 구간): LBA 5480..5487→$7A/$7B, 5488..5491→$7E(텍스트),
    5492..5493→$6D 앞 4KB(인덱스). 미사용 바이트는 트랩 패턴(00 E7) 유지.

입력: canary BIN(로더 훅 포함) + btrack_b4_field_payload.json
출력: Tenshi..._btrack_b4_field.bin/.cue + manifest
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARY_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9d_a2_canary.bin"
CANARY_SHA256 = "3CD8637BBC4C225C40C8A796C3A2CA102640B43D94CACF2E8BC69C61E4DDD3B0"
ORIGINAL_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
ENGINE_ID = ROOT / "module_relink" / "linked_identity" / "field.main_engine_lba0258_s20.bin"
PAYLOAD = ROOT / "translation" / "btrack_b4_field_payload.json"
DISASM = ROOT / "tools" / "huc6280_disasm_verifier" / "bin" / "Debug" / "net8.0" / "huc6280_disasm_verifier.exe"

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b4_field"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "btrack_b4_hook_manifest.json"

DATA_TRACK = 7_914_480
ENGINE_LBA = 258
ENGINE_ISO = ENGINE_LBA * 2048

# 코드 배치 (logical, bank $80 → engine offset = logical - 0x4000)
REGION_A = (0x4F12, 0x4FA1)     # dispatch + serve + state
REGION_B = (0x4C50, 0x4CD2)     # armchk
# REGION_C 는 게임 시작(엔진 init) 경로 사용 실측(2026-08-22 V3c 이분)으로 폐기.
# 프렐류드+match 는 region A 후미에 배치한다.
FLAG, TBANK, KB, KH, CURL, CURH = 0x4F9B, 0x4F9C, 0x4F9D, 0x4F9E, 0x4F9F, 0x4FA0
# serve 진입은 region A 내부 라벨로만 참조

# 풀 배치
POOL = [  # (lba, sectors, bank)
    (5480, 4, 0x7A), (5484, 4, 0x7B), (5488, 4, 0x7E), (5492, 2, 0x6D)
]
TEXT_BANKS = [0x7A, 0x7B, 0x7E]
BANK_SIZE = 8192
INDEX_BANK = 0x6D
INDEX_CAP = 4096
TRAP = bytes((0x00, 0xE7))
# 로더 훅 v2: 풀 상주를 482 컨텍스트로 한정 (2026-08-23 전투 깨짐 근본 수정)
# 부분 로드(96섹터 미만)가 표준인 이 게임에서, 비-482 로드 직전에 풀 뱅크를
# 원본 482 바이트로 복원해 "원본과 동일한 잔존 메모리 의미론"을 보존한다.
LOADER_HOOK_ADDR = 0xC737
PRESENT_ADDR = 0xC8FE          # pool_present 상태 (FF 창 끝, 디스크 초기값 0)
LOADER_WINDOW_END = 0xC8FE
POOL_ROWS = [(5480, 8, 0x7A), (5488, 4, 0x7E), (5492, 2, 0x6D)]
RESTORE_ROWS = [(554, 8, 0x7A), (570, 4, 0x7E), (502, 2, 0x6D)]  # 482 패키지 원본
INDEX_MAGIC = bytes((0x42, 0xB4))   # 'B'트랙 b4 — armchk가 인덱스 유효성 검증에 사용


# ---- 미니 어셈블러 -----------------------------------------------------------

class Asm:
    def __init__(self, origin: int):
        self.origin = origin
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []   # (pos, kind, label)

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

    def jmp(self, target):
        self.emit(0x4C)
        if isinstance(target, str):
            self.fixups.append((len(self.buf), "abs", target))
            self.emit(0x00, 0x00)
        else:
            self.emit(target & 0xFF, target >> 8)

    def resolve(self, external: dict[str, int]):
        table = {**external, **self.labels}
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


def asm_loader_hook_v2() -> bytes:
    """canary 훅 대체: 482 로드 시 풀 적재+PRESENT=1, 그 외 mode-06 로드 직전
    풀 뱅크를 원본 482 바이트로 복원(+PRESENT=0). P/A/X/Y·zp $F8-$FF 보존."""
    a = Asm(LOADER_HOOK_ADDR)
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
    a.emit(0x08, 0x48)                             # PHP PHA — post-load P/A 보존
    a.emit(0xA9, 0x00)                             # A = 풀 테이블 오프셋
    a.emit(0x20, 0x00, 0x00)                       # JSR RUN (fixup)
    a.fixups.append((len(a.buf) - 2, "abs", "run"))
    a.emit(0xA9, 0x01, 0x8D, PRESENT_ADDR & 0xFF, PRESENT_ADDR >> 8)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)           # STZ FLAG
    a.emit(0x68, 0x28)                             # PLA PLP — post-load 값 복원
    a.emit(0x60)                                   # RTS
    a.label("notf")
    a.emit(0xAD, PRESENT_ADDR & 0xFF, PRESENT_ADDR >> 8)
    a.branch(0xF0, "tail")
    a.emit(0xA9, 0x10)                             # A = 복원 테이블 오프셋 (풀 3행+FF)
    a.emit(0x20, 0x00, 0x00)
    a.fixups.append((len(a.buf) - 2, "abs", "run"))
    a.emit(0x9C, PRESENT_ADDR & 0xFF, PRESENT_ADDR >> 8)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.label("tail")
    a.emit(0x4C, 0x09, 0xE0)                       # JMP $E009
    # --- RUN: A=테이블 오프셋, 프레임 보존 후 FF 종결 행까지 read 반복 ---
    a.label("run")
    a.emit(0x08, 0x48, 0xDA, 0x5A)                 # PHP PHA PHX PHY
    a.emit(0xAA)                                   # TAX (오프셋)
    for zp in range(0xF8, 0x100):
        a.emit(0xA5, zp, 0x48)                     # LDA zp PHA
    a.label("loop")
    a.emit(0xBD, 0x00, 0x00)                       # LDA TBL,X (fixup)
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
    a.branch(0x80, "loop")                         # BRA loop
    a.label("endrun")
    for zp in range(0xFF, 0xF7, -1):
        a.emit(0x68, 0x85, zp)                     # PLA STA zp (역순)
    a.emit(0x7A, 0xFA, 0x68, 0x28)                 # PLY PLX PLA PLP
    a.emit(0x60)                                   # RTS
    a.label("tbl")
    for lba, cnt, bank in POOL_ROWS:
        a.emit((lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF, cnt, bank)
    a.emit(0xFF)
    for lba, cnt, bank in RESTORE_ROWS:
        a.emit((lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF, cnt, bank)
    a.emit(0xFF)
    # abs+N fixup 해석
    table = dict(a.labels)
    for pos, kind, name in list(a.fixups):
        if kind.startswith("abs+"):
            delta = int(kind[4:])
            addr = table[name] + delta
            a.buf[pos] = addr & 0xFF
            a.buf[pos + 1] = addr >> 8
            a.fixups.remove((pos, kind, name))
    code = a.resolve({})
    if LOADER_HOOK_ADDR + len(code) > LOADER_WINDOW_END:
        raise ValueError(f"loader hook v2 {len(code)}B — 창 초과")
    return code


def asm_region_a() -> "Asm":
    a = Asm(REGION_A[0])
    # dispatch — native 임시 문자열($55)이 활성이면 원본 경로에 양보한다.
    # (native ptr54 는 NUL 에서 STZ $54/$55 후 $4284 재진입하므로, 그 직후
    #  이 디스패치가 FLAG 를 보고 우리 스트림을 이어서 서비스한다 — 합성 안전)
    a.emit(0xA5, 0x55)                             # LDA $55
    a.branch(0xD0, "tonative")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)           # LDA FLAG
    a.branch(0xD0, "serve")
    a.jmp(REGION_B[0])                             # JMP armchk
    a.label("tonative")
    a.jmp(0x4284)
    a.label("serve")
    # 전용 커서(CURL/CURH)를 zp $00/$01 로 복사해 간접 읽기.
    # ($00/$01 은 원본 $4036 기본 경로 헬퍼($4255)가 매 호출 덮어쓰므로
    #  호출자는 어차피 이 zp 를 $4036 호출 너머로 보존한다고 가정할 수 없다)
    a.emit(0x43, 0x20)                             # TMA #$20 (MPR5)
    a.emit(0x48)                                   # PHA
    a.emit(0xAD, TBANK & 0xFF, TBANK >> 8)         # LDA TBANK
    a.emit(0x53, 0x20)                             # TAM #$20
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x85, 0x00)   # LDA CURL STA $00
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x85, 0x01)   # LDA CURH STA $01
    a.emit(0xB2, 0x00)                             # LDA ($00)
    a.branch(0xF0, "nul")
    a.emit(0x8D, 0x80, 0x2D)                       # STA $2D80
    a.emit(0xEE, CURL & 0xFF, CURL >> 8)           # INC CURL
    a.branch(0xD0, "nohi")
    a.emit(0xEE, CURH & 0xFF, CURH >> 8)           # INC CURH
    a.label("nohi")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0xAD, 0x80, 0x2D)                       # LDA $2D80
    a.emit(0x60)                                   # RTS
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)           # STZ FLAG
    a.jmp(0x4284)                                  # 원본 00 소비 → 종료·재개 보존
    # ---- 프렐류드: 인덱스 매직 검증 ----
    a.label("cpre")
    a.emit(0xAD, 0x00, 0xA0)                       # LDA $A000
    a.emit(0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "cfail")
    a.emit(0xAD, 0x01, 0xA0)                       # LDA $A001
    a.emit(0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "cfail")
    a.jmp("bcont")
    a.label("cfail")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.jmp(0x4284)
    # ---- match: 엔트리 채택 ----
    a.label("match2")
    a.emit(0xA0, 0x02)                             # LDY #2
    a.emit(0xB1, 0x00)                             # tbank
    a.emit(0x8D, TBANK & 0xFF, TBANK >> 8)
    a.emit(0xC8, 0xB1, 0x00)                       # addr_lo
    a.emit(0x8D, CURL & 0xFF, CURL >> 8)
    a.emit(0xC8, 0xB1, 0x00)                       # addr_hi
    a.emit(0x8D, CURH & 0xFF, CURH >> 8)
    a.emit(0xC8, 0xB1, 0x00)                       # (len-1)_lo — 인덱스에 len-1 저장
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)           # CLC ADC $4B STA $4B
    a.emit(0xC8, 0xB1, 0x00)                       # (len-1)_hi
    a.emit(0x65, 0x4C, 0x85, 0x4C)                 # ADC $4C STA $4C → 원문 terminator 위치
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)
    a.jmp("serve")
    return a


def asm_region_b() -> bytes:
    a = Asm(REGION_B[0])
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "pass0")
    a.emit(0xA5, 0x53)
    a.branch(0xD0, "pass0")
    a.emit(0xAD, 0x69, 0x2E)                       # LDA $2E69
    a.branch(0xD0, "pass0")
    a.emit(0xA5, 0x4C)                             # LDA $4C
    a.emit(0xC9, 0x80)
    a.branch(0x90, "pass0")                        # BCC
    a.emit(0xC9, 0xE0)
    a.branch(0xB0, "pass0")                        # BCS
    a.emit(0x4A, 0x4A, 0x4A, 0x4A, 0x4A)           # LSR x5 → hi>>5 (4..6)
    a.emit(0x18, 0x69, 0x08)                       # CLC ADC #$08
    a.emit(0x6D, 0xD0, 0x22)                       # ADC $22D0  (carry 불가: 12..14)
    a.emit(0x38, 0xE9, 0x68)                       # SEC SBC #$68
    a.emit(0xC9, 0x18)
    a.branch(0xB0, "pass0")                        # rel bank >= 24 → pass
    a.emit(0x8D, KB & 0xFF, KB >> 8)               # STA KB
    a.emit(0xA5, 0x4C, 0x29, 0x1F)                 # LDA $4C AND #$1F
    a.emit(0x8D, KH & 0xFF, KH >> 8)               # STA KH
    a.emit(0xDA, 0x5A)                             # PHX PHY
    a.emit(0x43, 0x20, 0x48)                       # TMA #$20 PHA
    a.emit(0xA9, INDEX_BANK, 0x53, 0x20)           # LDA #$6D TAM #$20
    a.jmp("cpre")                                  # → 매직 검증 프렐류드 (region A)
    a.label("bcont")
    a.emit(0xAD, KB & 0xFF, KB >> 8)               # LDA KB
    a.emit(0x0A, 0xAA)                             # ASL TAX
    a.emit(0xBD, 0x02, 0xA0, 0x85, 0x00)           # LDA $A002,X STA $00
    a.emit(0xBD, 0x03, 0xA0, 0x85, 0x01)           # LDA $A003,X STA $01
    a.emit(0xA0, 0x00)                             # LDY #0
    a.label("loop")
    a.emit(0xB1, 0x00)                             # LDA ($00),Y  (off_hi)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "rpass")
    a.emit(0xCD, KH & 0xFF, KH >> 8)               # CMP KH
    a.branch(0xD0, "next")
    a.emit(0xC8, 0xB1, 0x00, 0x88)                 # INY LDA ($00),Y DEY (off_lo)
    a.emit(0xC5, 0x4B)                             # CMP $4B
    a.branch(0xF0, "match")
    a.label("next")
    a.emit(0x18, 0xA5, 0x00, 0x69, 0x07, 0x85, 0x00)   # $00 += 7
    a.branch(0x90, "loop")                         # BCC loop
    a.emit(0xE6, 0x01)                             # INC $01
    a.branch(0x80, "loop")                         # BRA loop
    a.label("rpass")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.label("pass0")
    a.jmp(0x4284)
    a.label("match")
    a.fixups.append((len(a.buf) + 1, "abs", "match2"))
    a.emit(0x4C, 0x00, 0x00)
    return a


def asm_region_c(b_labels) -> bytes:
    a = Asm(REGION_C[0])
    # 프렐류드: bank $6D 가 유효한 인덱스인지 매직 검증 (인덱스 미탑재 상태에서
    # 쓰레기 포인터를 걷는 것을 차단 — 2026-08-22 검은 화면 근본 원인 수정)
    a.emit(0xAD, 0x00, 0xA0)                       # LDA $A000
    a.emit(0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "cfail")
    a.emit(0xAD, 0x01, 0xA0)                       # LDA $A001
    a.emit(0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "cfail")
    a.jmp(b_labels["bcont"])                       # 유효 → 버킷 걷기로 복귀
    a.label("cfail")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20 (MPR5 복원)
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.jmp(0x4284)
    a.label("match2")
    # 진입: ($00)=entry, Y 임의, MPR5=$6D, 스택: [MPR5][Y][X]
    a.emit(0xA0, 0x02)                             # LDY #2
    a.emit(0xB1, 0x00)                             # tbank
    a.emit(0x8D, TBANK & 0xFF, TBANK >> 8)
    a.emit(0xC8, 0xB1, 0x00, 0x85, 0x54)           # addr_lo → $54
    a.emit(0xC8, 0xB1, 0x00, 0x85, 0x55)           # addr_hi → $55
    a.emit(0xC8, 0xB1, 0x00)                       # len_lo
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)           # CLC ADC $4B STA $4B
    a.emit(0xC8, 0xB1, 0x00)                       # len_hi
    a.emit(0x65, 0x4C, 0x85, 0x4C)                 # ADC $4C STA $4C
    a.emit(0xA5, 0x4B)                             # 16-bit dec
    a.branch(0xD0, "nolo")
    a.emit(0xC6, 0x4C)                             # DEC $4C
    a.label("nolo")
    a.emit(0xC6, 0x4B)                             # DEC $4B
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM #$20
    a.emit(0x7A, 0xFA)                             # PLY PLX
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)   # FLAG=1
    a.jmp(SERVE)
    return a


# ---- 인덱스·풀 패킹 ----------------------------------------------------------

def pack_pool(records):
    banks = {b: bytearray() for b in TEXT_BANKS}
    placed = {}
    for r in sorted(records, key=lambda r: -r["encoded_length"]):
        data = bytes.fromhex(r["encoded_hex"])
        if 0 in data[:-1]:
            raise ValueError(f"{r['id']}: 내부 00 바이트 — serve 조기 종료 위험")
        for b in TEXT_BANKS:
            if len(banks[b]) + len(data) <= BANK_SIZE:
                placed[r["id"]] = (b, len(banks[b]))
                banks[b].extend(data)
                break
        else:
            raise ValueError(f"{r['id']}: 텍스트 뱅크 공간 부족")

    buckets: dict[int, list] = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, boff = placed[r["id"]]
        buckets[kb].append((
            (off13 >> 8) & 0x1F, off13 & 0xFF, bank,
            0xA000 + boff, r["original_raw_length"]))

    entry_area = bytearray()
    bucket_ptrs = []
    base = 0xA000 + 2 + 24 * 2          # magic(2B) + bucket table 뒤
    for kb in range(24):
        bucket_ptrs.append(base + len(entry_area))
        for off_hi, off_lo, bank, addr, ln in sorted(buckets[kb]):
            lm1 = ln - 1
            entry_area.extend((off_hi, off_lo, bank,
                               addr & 0xFF, addr >> 8, lm1 & 0xFF, lm1 >> 8))
        entry_area.append(0xFF)
    index = bytearray(INDEX_MAGIC)          # $A000/$A001 = 매직 서명
    for p in bucket_ptrs:
        index.extend((p & 0xFF, p >> 8))
    index.extend(entry_area)
    if len(index) > INDEX_CAP:
        raise ValueError(f"인덱스 {len(index)}B > {INDEX_CAP}")
    return banks, bytes(index), placed


# ---- 빌드 --------------------------------------------------------------------

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    canary = bytearray(CANARY_BIN.read_bytes())
    if sha256(bytes(canary)).upper() != CANARY_SHA256:
        raise ValueError("canary BIN 해시 불일치")
    engine = ENGINE_ID.read_bytes()
    # 엔진 identity 확인 (canary 는 엔진 bank81/84 에 로더 훅 패치가 있으므로
    # bank $80 영역만 identity 와 대조)
    disc_engine_off = DATA_TRACK + ENGINE_ISO
    if bytes(canary[disc_engine_off:disc_engine_off + 0x2000]) != engine[:0x2000]:
        raise ValueError("canary BIN 의 엔진 bank $80 이 identity 와 다름")

    a_asm = asm_region_a()                    # pass1: cpre/match2 라벨 확보
    b_asm = asm_region_b()
    code_b = b_asm.resolve({"cpre": a_asm.labels["cpre"],
                            "match2": a_asm.labels["match2"]})
    code_a = a_asm.resolve({"bcont": b_asm.labels["bcont"]})
    for name, code, (start, end) in (("A", code_a, REGION_A),
                                     ("B", code_b, REGION_B)):
        cap = end - start
        # state 4B 는 region A 캡 안에서 코드와 별도
        limit = (FLAG - REGION_A[0]) if name == "A" else cap   # state 앞까지만
        if len(code) > limit:
            raise ValueError(f"region {name} 코드 {len(code)}B > 한도 {limit}B")

    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    records = payload["records"]
    banks, index, placed = pack_pool(records)

    patches = []      # (disc_offset, bytes, 설명)

    def patch(disc_off, data, why):
        patches.append((disc_off, bytes(data), why))

    # 벡터 + 코드 (엔진 bank $80: logical-0x4000 = 파일 오프셋)
    patch(disc_engine_off + 0x36, bytes((0x4C, REGION_A[0] & 0xFF, REGION_A[0] >> 8)),
          "$4036 vector → new dispatch")
    patch(disc_engine_off + (REGION_A[0] - 0x4000), code_a, "region A dispatch+serve")
    patch(disc_engine_off + (FLAG - 0x4000), bytes(6), "state FLAG/TBANK/KB/KH/CUR = 0")
    patch(disc_engine_off + (REGION_B[0] - 0x4000), code_b, "region B armchk")
    hook2 = asm_loader_hook_v2()
    patch(disc_engine_off + (LOADER_HOOK_ADDR - 0x4000), hook2,
          "loader hook v2 (pool scope = 482 only)")
    patch(disc_engine_off + (PRESENT_ADDR - 0x4000), bytes(1), "pool_present = 0")
    # 콜사이트는 $66FC 만 훅 경유. 근거(2026-08-23 런타임 호출자 추적): 모든 장면
    # 로드(482/290/2882)가 $66FC 로 발행됨. $6B5D/$8B78 은 실행 컨텍스트(MPR6)가
    # 미검증이라 패치 시 탑 이벤트 전투에서 흰 화면 멈춤 유발 — 원복.
    # 풀이 존재하는 동안의 로드는 $66FC 경유가 실측이므로 복원 커버리지 손실 없음.
    for cs_logical in (0x66FC,):
        cs_off = disc_engine_off + (cs_logical - 0x4000)
        cur = bytes(out_probe[cs_off:cs_off + 3]) if False else None
        patch(cs_off, bytes((0x20, LOADER_HOOK_ADDR & 0xFF, LOADER_HOOK_ADDR >> 8)),
              f"callsite ${cs_logical:04X} -> JSR $C737")

    # 풀: 텍스트 뱅크 + 인덱스 (잔여는 트랩 패턴 유지)
    for lba, sectors, bank in POOL:
        blob = index if bank == INDEX_BANK else bytes(banks[bank])
        cap = sectors * 2048
        pad = bytearray()
        while len(blob) + len(pad) < cap:
            pad.extend(TRAP)
        patch(DATA_TRACK + lba * 2048, (blob + bytes(pad))[:cap],
              f"pool bank ${bank:02X} @LBA {lba}")

    out = bytearray(canary)
    original_hex = {}
    for off, data, why in patches:
        original_hex[why] = bytes(out[off:off + len(data)]).hex().upper()[:120]
        out[off:off + len(data)] = data
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(ORIGINAL_CUE.read_text(encoding="ascii")
                       .replace("Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin",
                                OUT_BIN.name), encoding="ascii")

    # 디스어셈블 검산
    disasm = {}
    for name, (start, _), code in (("A", REGION_A, code_a),
                                   ("B", REGION_B, code_b)):
        r = subprocess.run(
            [str(DISASM), "--raw", str(OUT_BIN), f"{start:X}",
             f"{disc_engine_off + (start - 0x4000):X}", f"{len(code):X}"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"region {name} disasm FAIL:\n{r.stdout}\n{r.stderr}")
        disasm[name] = r.stdout.strip().splitlines()

    manifest = {
        "format": "BTRACK-B4-FIELD-HOOK-BUILD",
        "runtime_status": "PENDING",
        "base": {"canary_bin_sha256": CANARY_SHA256},
        "code": {
            "vector": "$4036: JMP $4284 -> JMP $4F12",
            "region_a": {"addr": f"{REGION_A[0]:#06x}", "bytes": len(code_a),
                         "hex": code_a.hex().upper()},
            "region_b": {"addr": f"{REGION_B[0]:#06x}", "bytes": len(code_b),
                         "hex": code_b.hex().upper()},

            "state": {"FLAG": f"{FLAG:#06x}", "TBANK": f"{TBANK:#06x}",
                      "KB": f"{KB:#06x}", "KH": f"{KH:#06x}"},
            "disasm": disasm,
        },
        "pool": {
            "text_bytes": {f"{b:02X}": len(banks[b]) for b in TEXT_BANKS},
            "index_bytes": len(index),
            "records": len(records),
        },
        "original_bytes_replaced": original_hex,
        "known_gaps": [
            "Memo 포인터 레코드 7건은 ptr52 경로라 v1 미적용 (일본어 유지)",
            "battle/menu 등 다른 renderer 원문은 아직 일본어 (Z9 확대 대상)",
        ],
        "runtime_gate": [
            "첫 필드 진입 시 첫 대사가 전면 한글로 표시",
            "회귀: 첫 대사 → NPC 전원 → Memo → 건물 → 전투·복귀 → 탑 → 초상화",
            "화면 깨짐·EXEC BRK·멈춤·오디오 이상 0건",
            "대사 종료 후 이벤트 진행(선택지·이동)이 원본과 동일",
        ],
        "output_bin_sha256": sha256(bytes(out)),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({
        "status": "BUILD_OK",
        "code_bytes": {"A": len(code_a), "B": len(code_b)},
        "pool_text": {f"{b:02X}": len(banks[b]) for b in TEXT_BANKS},
        "index_bytes": len(index),
        "bin": OUT_BIN.name,
        "sha256": manifest["output_bin_sha256"][:16],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
