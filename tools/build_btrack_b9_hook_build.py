#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B9 — 전 씬(54) 텍스트 카드 상주 (Z9_b9_카드_확장_설계.md §2·§3.5).

b8.3 대비 변경:
  1. **카드 768KB**: $00-$1F = b8.3 기반 카드(btrack_full) + 씬 테이블,
     확장 = 전역 유니크 텍스트 풀(FFD, 레코드는 8KB 뱅크 경계 불가침) +
     씬별 인덱스(256B 정렬, 뱅크당 다씬). **뱅크 $40-$43 은 사용 금지 —
     Arcade Card RAM 창이 카드 ROM 을 가린다** (b9 v1 행업/v2 무장 실패의
     진범, 2026-08-28 진단 lua 물리 버스 실측). 실측: 유니크 2,747레코드
     263,135B = 33뱅크($20-$3F,$44) + 인덱스 11뱅크($45-$4F).
  2. **armchk_v3**: 인덱스 base 파라미터화 — 매직/버킷 ptr 를
     (SCRATCH+5)<<8 기준 zp 간접으로 읽는다. SCRATCH_KH 는 $AFFE(카드 ROM
     — 쓰기 불가)에서 엔진 RAM $C8FD 로 이동. 코드는 기본 카드 $1F
     폰트 꼬리(논리 $7A00) 단일 사본, 리더 v3m 이 MPR3=$1F 브래킷으로
     호출한다 (b9 v2 런에서 실행·정상 복귀 실증).
  3. **RAM 풀·디스크 풀 섹터 전면 폐지**: 씬 RAM 뱅크 무사용 — play-CDL·
     init-coverage·복원 행·정적 자산 지도 가드 전부 불필요. 디스크 변경 =
     엔진 패치(벡터/bank81/창/state) + 트랙 확장(+1024, 유지 권장안)뿐.
  4. **로더 v4·리더 v2 무변경**: 행 이미지 = [FF,FF,FF,FF,IBANK,IBASE_HI,
     FF…]+[FF×21] — RUN 은 byte0=FF 로 무동작, 비매치 PRESENT=0 은 stale
     인덱스 안전판으로 유지(§3.5-2).

전제 런타임 실증: 512KB $20 read (b9poc) + 768KB $4B read (b9poc_768k4B).
출력: *_btrack_b9.bin/.cue + probes/SystemCard3_btrack_b9.pce (768KB)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_hook_build import (
    Asm, make_slice, asm_bank81,
    T2, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP, WINDOW_LO, LOADER,
    SCRATCH, WINDOW_CODE_END, FLAG, TBANK, CURL, CURH, PRESENT, WINDOW_HI,
    ROWS_IMG_LEN, ENTRY_LEN, BANK_SIZE, INDEX_MAGIC,
    CARD_TABLE_OFF, SRC_BIN, SRC_SHA256, SRC_CUE, CARD_SRC, DISASM,
)
from build_btrack_b7_6_hook_build import FONT_TAIL
from build_btrack_b8_hook_build import (
    ARMCHK, EXT_SECTORS, INS_OFF, asm_loader_v4, shift_cue,
)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b9"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b9.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b9_hook_manifest.json"
MODULE_CATALOG = ROOT / "translation" / "ziria_module_catalog.json"

SECTOR = 2048
CARD_SIZE = 768 * 1024
EXT_FIRST_BANK = 0x20
ARMCHK_OFF = ARMCHK - 0xA000        # 인덱스 뱅크 내 예약 홀 = 0x880 (미사용 FF)
IBASE = SCRATCH + 5                 # 씬별 인덱스 base hi (행 이미지 byte5)
SCRATCH_KH_V3 = 0xC8FD              # armchk 키 hi 스크래치 (엔진 RAM)
# armchk_v4 스트림 선택용 (SCRATCH 끝 $C8F1 과 FLAG $C8F9 사이 미사용 7B)
PTRL_V4, PTRH_V4, STREAM_V4 = 0xC8F2, 0xC8F3, 0xC8F4

# 사용 가능 확장 뱅크 (2026-08-28 b9 v1/v2 진단 lua 실측으로 확정):
# **물리 뱅크 $40-$43 은 Arcade Card RAM 창이 카드 ROM 을 가린다**
# (TurboNyma/Mednafen — phys 0x84000 이 카드의 42B4 대신 0000 반환 실측).
# b9 v1 행업의 진범 = 인덱스 뱅크 $41+ 의 JSR $A880 fetch 가 00(=BRK)로
# 읽힌 것 ("확장 뱅크 fetch 불가"는 오진 — 섀도우 문제였음). b9 v2 무장
# 실패도 동일 원인(인덱스 $41-$43 이 00 으로 읽혀 매직 불일치 → 원문 폴백).
EXT_BANKS = list(range(0x20, 0x40)) + list(range(0x44, 0x60))

# armchk_v3 실행 위치: 기본 카드 뱅크 $1F 폰트 꼬리(테이블 뒤) 단일 사본,
# 리더 v3m 이 MPR3=$1F 브래킷으로 $7A00 을 호출. b9 v2 런에서 20k 프레임
# 실행·정상 복귀 실증(무장 실패는 위 섀도우 원인). 확장 뱅크에서의 명령
# fetch 는 비섀도우 뱅크에선 미검증 — 검증할 이유가 없어 $1F 유지.
ARMCHK_EXEC = 0x7A00                # MPR3 창 $6000-$7FFF, bank $1F off 0x1A00
ARMCHK_CARD_OFF = 0x1F * BANK_SIZE + (ARMCHK_EXEC - 0x6000)   # = 0x3FA00

# 전 overlay 씬 (54 — show_scene_lba_pcehawk.lua/모듈 카탈로그 실측).
SCENES_B9 = [290, 386, 482, 578, 674, 770, 866, 962, 1058, 1154, 1250, 1346,
             1442, 1538, 1634, 1730, 1826, 1922, 2018, 2114, 2210, 2306,
             2402, 2498, 2594, 2690, 2786, 2882, 2978, 3074, 3170, 3266,
             3362, 3458, 3554, 3650, 3746, 3842, 3938, 4034, 4130, 4226,
             4322, 4418, 4514, 4610, 4706, 4802, 4898, 4994, 5090, 5186,
             5282, 5378]


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


_SUPPLEMENT_CACHE: dict | None = None


def _supplement() -> dict:
    """master 추출 누락 보충 페이로드 (build_btrack_b9_gap_supplement.py).
    필수 입력 — 없으면 빌드 불가 (2026-08-28 지진 대사 등 18레코드)."""
    global _SUPPLEMENT_CACHE
    if _SUPPLEMENT_CACHE is None:
        _SUPPLEMENT_CACHE = json.loads(
            (ROOT / "translation" / "btrack_b9_gap_supplement_payload.json"
             ).read_text(encoding="utf-8"))["scenes"]
    return _SUPPLEMENT_CACHE


def payload(lba: int):
    name = ("btrack_b4_field_payload.json" if lba == 482
            else f"btrack_b7_scene_{lba}_payload.json")
    records = json.loads((ROOT / "translation" / name
                          ).read_text(encoding="utf-8"))["records"]
    return records + _supplement().get(str(lba), [])


# ---- 리더 v3m (v2 + armchk 호출을 MPR3=$1F 브래킷 $7A00 으로) ----------------

def asm_reader_v3m(origin: int) -> Asm:
    a = Asm(origin)
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)                             # TMA5 PHA
    a.emit(0xAD, (SCRATCH + 4) & 0xFF, (SCRATCH + 4) >> 8)
    a.emit(0x53, 0x20)                                   # MPR5 = IBANK (인덱스)
    a.emit(0x43, 0x08, 0x48)                             # TMA3 PHA
    a.emit(0xA9, 0x1F, 0x53, 0x08)                       # MPR3 = $1F (armchk 코드)
    a.jsr(ARMCHK_EXEC)
    a.emit(0x68, 0x53, 0x08)                             # MPR3 복원 (carry 보존)
    a.emit(0x68, 0x53, 0x20)                             # MPR5 복원
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


# ---- armchk_v3 (인덱스 base 파라미터화 + KH → 엔진 RAM) ----------------------

def asm_armchk_v3() -> bytes:
    a = Asm(ARMCHK_EXEC)
    a.emit(0xDA, 0x5A)                                   # PHX PHY
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
    a.emit(0xAA)                                         # TAX (kb)
    # 매직 검사 @ (IBASE<<8) — zp $00/$01 간접 (이 컨텍스트에서 클로버 허용,
    # b6+ armchk 가 동일하게 사용해 게이트 실증됨)
    a.emit(0x64, 0x00)                                   # STZ $00
    a.emit(0xAD, IBASE & 0xFF, IBASE >> 8)               # LDA IBASE
    a.emit(0x85, 0x01)                                   # STA $01
    a.emit(0xA0, 0x00)                                   # LDY #0
    a.emit(0xB1, 0x00, 0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "p0")
    a.emit(0xC8, 0xB1, 0x00, 0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "p0")
    a.branch(0x80, "cont")
    a.label("p0")
    a.jmp("pass")
    a.label("cont")
    a.emit(0xA5, 0x4C, 0x29, 0x1F)
    a.emit(0x8D, SCRATCH_KH_V3 & 0xFF, SCRATCH_KH_V3 >> 8)
    # 버킷 ptr @ base+2+2*kb → $00/$01
    a.emit(0x8A, 0x0A)                                   # TXA ASL (kb<=23)
    a.emit(0x18, 0x69, 0x02)                             # CLC ADC #2
    a.emit(0xA8)                                         # TAY
    a.emit(0xB1, 0x00, 0x48)                             # LDA ($00),Y PHA
    a.emit(0xC8, 0xB1, 0x00)                             # INY LDA ($00),Y
    a.emit(0x85, 0x01)                                   # STA $01 (ptr hi)
    a.emit(0x68, 0x85, 0x00)                             # PLA STA $00
    a.label("loop")
    a.emit(0xA0, 0x00)
    a.emit(0xB1, 0x00)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "pass")
    a.emit(0xCD, SCRATCH_KH_V3 & 0xFF, SCRATCH_KH_V3 >> 8)
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


def asm_armchk_v4() -> bytes:
    """armchk_v3 + **$53 스트림 지원** (2026-08-30).

    엔진 디스패처 $4284 실측: `$55`≠0 → zp $54/$55, `$53`≠0 → **zp $52/$53**
    (메모·초상화), `$2E69`≠0 → 별도, 기본 → zp $4B/$4C. v3 는 `$53`≠0 을
    무조건 거부해 메모·초상화 대사가 일문으로 남았다.

    키 공간이 동일함을 세이브스테이트로 확인(메모 화면 $52=31/$53=C0 →
    소스키 0x10031 = ISO 0xA1031 'ダーク教のこと'). 따라서 **포인터 쌍만
    바꾸면** 된다: 진입 시 활성 포인터를 PTRL/PTRH 에 복사해 키 산출·비교를
    절대주소로 하고, 매치 시 STREAM 값에 따라 원래 zp 쌍을 전진시킨다.

    `$55`≠0 은 리더 v3m 이 이미 native 로 보내므로 여기선 검사하지 않는다.
    """
    a = Asm(ARMCHK_EXEC)
    a.emit(0xDA, 0x5A)                                   # PHX PHY
    # 우선순위는 디스패처($4284)와 같아야 한다: $53 이 $2E69 보다 앞선다.
    # ($55 은 리더 v3m 이 이미 native 로 보냄)
    a.emit(0xA5, 0x53)                                   # LDA $53
    a.branch(0xF0, "chk2e")
    a.emit(0x8D, PTRH_V4 & 0xFF, PTRH_V4 >> 8)           # STA PTRH
    a.emit(0xA5, 0x52, 0x8D, PTRL_V4 & 0xFF, PTRL_V4 >> 8)
    a.emit(0xA9, 0x01, 0x8D, STREAM_V4 & 0xFF, STREAM_V4 >> 8)
    a.branch(0x80, "have")
    a.label("chk2e")
    a.emit(0xAD, 0x69, 0x2E)                             # LDA $2E69
    a.branch(0xD0, "p0")
    a.emit(0xA5, 0x4C, 0x8D, PTRH_V4 & 0xFF, PTRH_V4 >> 8)
    a.emit(0xA5, 0x4B, 0x8D, PTRL_V4 & 0xFF, PTRL_V4 >> 8)
    a.emit(0x9C, STREAM_V4 & 0xFF, STREAM_V4 >> 8)       # STZ STREAM
    a.label("have")
    a.emit(0xAD, PTRH_V4 & 0xFF, PTRH_V4 >> 8, 0xC9, 0x80)
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
    a.emit(0x64, 0x00)                                   # STZ $00
    a.emit(0xAD, IBASE & 0xFF, IBASE >> 8)
    a.emit(0x85, 0x01)
    a.emit(0xA0, 0x00)
    a.emit(0xB1, 0x00, 0xC9, INDEX_MAGIC[0])
    a.branch(0xD0, "p0")
    a.emit(0xC8, 0xB1, 0x00, 0xC9, INDEX_MAGIC[1])
    a.branch(0xD0, "p0")
    a.branch(0x80, "cont")
    a.label("p0")
    a.jmp("pass")
    a.label("cont")
    a.emit(0xAD, PTRH_V4 & 0xFF, PTRH_V4 >> 8, 0x29, 0x1F)
    a.emit(0x8D, SCRATCH_KH_V3 & 0xFF, SCRATCH_KH_V3 >> 8)
    a.emit(0x8A, 0x0A)
    a.emit(0x18, 0x69, 0x02)
    a.emit(0xA8)
    a.emit(0xB1, 0x00, 0x48)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x85, 0x01)
    a.emit(0x68, 0x85, 0x00)
    a.label("loop")
    a.emit(0xA0, 0x00)
    a.emit(0xB1, 0x00)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "pass")
    a.emit(0xCD, SCRATCH_KH_V3 & 0xFF, SCRATCH_KH_V3 >> 8)
    a.branch(0xD0, "next")
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0xCD, PTRL_V4 & 0xFF, PTRL_V4 >> 8)           # CMP PTRL
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
    a.emit(0xC8, 0xB1, 0x00)                             # A = len lo
    a.emit(0xAE, STREAM_V4 & 0xFF, STREAM_V4 >> 8)       # LDX STREAM
    a.branch(0xD0, "adv53")
    a.emit(0x18, 0x65, 0x4B, 0x85, 0x4B)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x65, 0x4C, 0x85, 0x4C)
    a.branch(0x80, "armed")
    a.label("adv53")
    a.emit(0x18, 0x65, 0x52, 0x85, 0x52)
    a.emit(0xC8, 0xB1, 0x00)
    a.emit(0x65, 0x53, 0x85, 0x53)
    a.label("armed")
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)
    a.emit(0x7A, 0xFA)
    a.emit(0x18, 0x60)
    a.label("pass")
    a.emit(0x7A, 0xFA)
    a.emit(0x38, 0x60)
    return a.resolve()


DISPATCH = 0x4284                   # 엔진 스트림 디스패처 (리더 본체)
DISPATCH_SKIP = 0x4288              # $55 검사 4B 건너뛴 지점
DISPATCH_S55 = 0x42BA               # $55 스트림 본체


def asm_bank81_v2(wnd_slice: int, wnd_reader: int) -> bytes:
    """훅 지점을 `$4036` → **`$4284`(디스패처 본체)** 로 옮긴 트램펄린.

    2026-08-30 실측: 메모/초상화 대사는 `$4036` 을 경유하지 않아 리더가
    아예 호출되지 않는다(armchk 스크래치 FF 유지). 그 시점 zp `$53`≠0 로
    **$53 스트림 포인터가 설정돼 있으므로** 소비자는 디스패처를 직접
    호출한다고 판단, 훅을 디스패처 진입부로 옮긴다.

    `$4284` 의 앞 4B(`LDA $55 / BNE $42BA`)를 `JMP TRAMP` 로 덮으므로
    $55 분기는 트램펄린이 대신 수행하고, 미처리 시 `$4288`($53 검사)로
    복귀한다. `$4036` 벡터는 **원복**해야 이중 훅(무한 재진입)을 피한다.
    """
    a = Asm(SLICE_LO)
    a.jsr(wnd_slice)
    a.emit(0x80, 0x25)
    assert a.pc == TRAMP
    a.emit(0x43, 0x40, 0x48)                       # TMA #$40 PHA
    a.emit(0xA9, 0x84, 0x53, 0x40)                 # LDA #$84 TAM #$40
    a.jsr(wnd_reader)
    a.emit(0x68, 0x53, 0x40)                       # PLA TAM #$40 (carry 보존)
    a.branch(0xB0, "tonat")
    a.emit(0xAD, 0x80, 0x2D)                       # LDA $2D80
    a.emit(0x60)                                   # RTS
    a.label("tonat")
    a.emit(0xA5, 0x55)                             # LDA $55
    a.branch(0xF0, "n53")
    a.emit(0x4C, DISPATCH_S55 & 0xFF, DISPATCH_S55 >> 8)
    a.label("n53")
    a.emit(0x4C, DISPATCH_SKIP & 0xFF, DISPATCH_SKIP >> 8)
    code = a.resolve()
    assert len(code) <= SLICE_HI - SLICE_LO, f"bank81_v2 {len(code)}B > 42B"
    return code + bytes(SLICE_HI - SLICE_LO - len(code))


# 훅 지점 선택 (b12 드라이버가 True 로 바꾼다)
HOOK_DISPATCH = False

# armchk 빌더 선택 (b10/b11 드라이버가 교체 가능)
ARMCHK_BUILDER = asm_armchk_v3


# ---- 전역 풀 / 인덱스 ---------------------------------------------------------

def pack_global_pool(all_records):
    """유니크 encoded_hex → (bank, in_bank_off). FFD, 8KB 뱅크 경계 불가침."""
    uniq = sorted({r["encoded_hex"] for r in all_records},
                  key=lambda h: (-len(h), h))
    bins: list[int] = []            # 뱅크별 사용 바이트
    placed: dict[str, tuple[int, int]] = {}
    for h in uniq:
        data = bytes.fromhex(h)
        if 0 in data[:-1]:
            raise ValueError(f"내부 00: {h[:24]}…")
        if data[-1] != 0:
            raise ValueError(f"NUL 종료 아님: {h[:24]}…")
        if len(data) > BANK_SIZE:
            raise ValueError(f"레코드 {len(data)}B > 8KB")
        for i in range(len(bins)):
            if bins[i] + len(data) <= BANK_SIZE:
                placed[h] = (EXT_BANKS[i], bins[i])
                bins[i] += len(data)
                break
        else:
            placed[h] = (EXT_BANKS[len(bins)], 0)
            bins.append(len(data))
    return placed, bins


def build_index_b9(records, locate, base: int) -> bytes:
    buckets = {i: [] for i in range(24)}
    keys_seen = set()
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        if key in keys_seen:
            raise ValueError(f"{r['id']}: 씬 내 source key 중복 {key:06X}")
        keys_seen.add(key)
        kb, off13 = key >> 13, key & 0x1FFF
        bank, addr = locate(r["encoded_hex"])
        buckets[kb].append(((off13 >> 8) & 0x1F, off13 & 0xFF, bank,
                            addr, r["original_raw_length"]))
    entry_area = bytearray()
    ptrs = []
    ebase = base + 2 + 24 * 2
    for kb in range(24):
        ptrs.append(ebase + len(entry_area))
        for oh, ol, bank, addr, ln in sorted(buckets[kb]):
            lm1 = ln - 1
            entry_area.extend((oh, ol, bank, addr & 0xFF, addr >> 8,
                               lm1 & 0xFF, lm1 >> 8))
        entry_area.append(0xFF)
    index = bytearray(INDEX_MAGIC)
    for p in ptrs:
        index.extend((p & 0xFF, p >> 8))
    index.extend(entry_area)
    return bytes(index)


def place_indexes(scene_sizes: dict[int, int], first_slot: int,
                  armchk_len: int):
    """씬 인덱스를 256B 정렬 first-fit-decreasing 으로 인덱스 뱅크에 배치.
    뱅크 번호 = EXT_BANKS[first_slot + i] (Arcade Card 섀도우 $40-$43 스킵).
    뱅크당 구역 = [0x000,0x880) / [align256(0x880+armchk_len), 0x2000)."""
    rb = (ARMCHK_OFF + armchk_len + 0xFF) & ~0xFF
    banks: list[list[int]] = []     # 뱅크별 [구역A 커서, 구역B 커서]
    where: dict[int, tuple[int, int]] = {}   # lba -> (bank, off)
    for lba in sorted(scene_sizes, key=lambda l: -scene_sizes[l]):
        need = (scene_sizes[lba] + 0xFF) & ~0xFF
        for i, cur in enumerate(banks):
            if cur[0] + need <= ARMCHK_OFF:
                where[lba] = (EXT_BANKS[first_slot + i], cur[0])
                cur[0] += need
                break
            if cur[1] + need <= BANK_SIZE:
                where[lba] = (EXT_BANKS[first_slot + i], cur[1])
                cur[1] += need
                break
        else:
            banks.append([0, rb])
            bank = EXT_BANKS[first_slot + len(banks) - 1]
            if need <= ARMCHK_OFF:
                where[lba] = (bank, 0)
                banks[-1][0] = need
            else:
                where[lba] = (bank, rb)
                banks[-1][1] = rb + need
    return where, len(banks)


def rows_image_b9(ibank: int, ibase_hi: int) -> bytes:
    pool = bytearray(b"\xFF" * ROWS_IMG_LEN)
    pool[4] = ibank                 # SCRATCH+4 (리더 v2)
    pool[5] = ibase_hi              # SCRATCH+5 (armchk_v3)
    return bytes(pool) + b"\xFF" * ROWS_IMG_LEN


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 씬 모집단 가드: 전 씬이 overlay 디렉터리에 정확히 1종으로 존재
    catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))
    overlay = catalog["directories"]["overlay"]["entries"]
    for lba in SCENES_B9:
        n = len({(e["lba"], e["sector_count"]) for e in overlay
                 if e["lba"] == lba})
        if n != 1:
            raise ValueError(f"scene {lba}: overlay 엔트리 {n}종")

    # 엔진 사전검증 (b8.3 동일)
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42))
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65))
    assert slice_src[-2:] == bytes((0xD0, 0xD6))
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창 오염"

    # 창 조립
    loader = asm_loader_v4().resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader_v3m(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > WINDOW_CODE_END:
        raise ValueError(f"창 코드 초과: {wnd_end:#06x}")
    bank81 = (asm_bank81_v2 if HOOK_DISPATCH else asm_bank81)(
        wnd_slice_addr, wnd_reader_addr)
    armchk = ARMCHK_BUILDER()
    assert ARMCHK_OFF + len(armchk) <= 0xA00, f"armchk {len(armchk)}B 과대"
    assert ARMCHK_CARD_OFF + len(armchk) <= FONT_TAIL[1], "armchk 폰트 꼬리 초과"

    # 페이로드 적재 + 전역 풀
    payloads = {lba: payload(lba) for lba in SCENES_B9}
    all_records = [r for pl in payloads.values() for r in pl]
    placed, text_bins = pack_global_pool(all_records)
    n_text_banks = len(text_bins)

    def locate(h: str) -> tuple[int, int]:
        bank, off = placed[h]
        return bank, 0xA000 + off

    # 인덱스 배치 → 인덱스 이미지 (뱅크 = EXT_BANKS 슬롯, $40-$43 스킵)
    scene_sizes = {lba: 2 + 48 + 7 * len(pl) + 24
                   for lba, pl in payloads.items()}
    where, n_idx_banks = place_indexes(scene_sizes, n_text_banks, len(armchk))
    if n_text_banks + n_idx_banks > len(EXT_BANKS):
        raise ValueError(f"확장 뱅크 초과: {n_text_banks}+{n_idx_banks}"
                         f" > {len(EXT_BANKS)}")
    last_bank = EXT_BANKS[n_text_banks + n_idx_banks - 1]
    assert last_bank not in range(0x40, 0x44)
    assert (last_bank + 1) * BANK_SIZE <= CARD_SIZE

    indexes: dict[int, bytes] = {}
    for lba, pl in payloads.items():
        ibank, ioff = where[lba]
        idx = build_index_b9(pl, locate, 0xA000 + ioff)
        assert len(idx) == scene_sizes[lba]
        assert ioff % 0x100 == 0
        assert (ioff + len(idx) <= ARMCHK_OFF) or (ioff >= ARMCHK_OFF)
        indexes[lba] = idx

    # 디스크: 엔진 패치 + 트랙 확장만 (풀 섹터 없음)
    if HOOK_DISPATCH:
        # 벡터는 원복(원본 JMP $4284 유지) + 디스패처 진입부를 훅
        assert bytes(out[eng_off(DISPATCH):eng_off(DISPATCH) + 4]) ==             bytes((0xA5, 0x55, 0xD0, 0x32)), "디스패처 원본 불일치"
        hook_patch = [(eng_off(DISPATCH),
                       bytes((0x4C, TRAMP & 0xFF, TRAMP >> 8, 0xEA)),
                       "dispatch hook")]
    else:
        hook_patch = [(eng_off(VECTOR) + 1,
                       bytes((TRAMP & 0xFF, TRAMP >> 8)), "vector")]
    patches = hook_patch + [
               (eng_off(SLICE_LO), bank81, "bank81"),
               (eng_off(WINDOW_LO), loader + wslice + reader, "window code"),
               (eng_off(FLAG), bytes(6), "state=0")]
    for off, data, _ in patches:
        assert off + len(data) <= INS_OFF
        out[off:off + len(data)] = data
    out[INS_OFF:INS_OFF] = bytes(EXT_SECTORS * SECTOR)
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(shift_cue(SRC_CUE.read_text(encoding="ascii"),
                                 OUT_BIN.name, EXT_SECTORS), encoding="ascii")

    # 카드 조립
    card = bytearray(CARD_SRC.read_bytes())
    assert len(card) == 256 * 1024
    card.extend(b"\xFF" * (CARD_SIZE - len(card)))
    card_written: list[tuple[int, int, str]] = []

    # 1) 씬 테이블 (54 엔트리)
    table = bytearray()
    for lba in SCENES_B9:
        ibank, ioff = where[lba]
        table.extend(((lba >> 8) & 0xFF, lba & 0xFF))
        table.extend(rows_image_b9(ibank, (0xA000 + ioff) >> 8))
    table.append(0xFF)
    assert len(table) == len(SCENES_B9) * ENTRY_LEN + 1
    assert CARD_TABLE_OFF + len(table) <= ARMCHK_CARD_OFF, "테이블이 armchk 침범"
    assert set(card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)]) == {0xFF}
    card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)] = table
    card_written.append((CARD_TABLE_OFF, len(table), "scene table"))

    # 1b) armchk_v3 — 기본 카드 $1F 폰트 꼬리 (실행 실증 영역), 단일 사본
    assert set(card[ARMCHK_CARD_OFF:ARMCHK_CARD_OFF + len(armchk)]) == {0xFF}
    card[ARMCHK_CARD_OFF:ARMCHK_CARD_OFF + len(armchk)] = armchk
    card_written.append((ARMCHK_CARD_OFF, len(armchk), "armchk_v3 @1F"))

    # 2) 텍스트 풀
    bank_blobs: dict[int, bytearray] = {}
    for h, (bank, off) in placed.items():
        data = bytes.fromhex(h)
        blob = bank_blobs.setdefault(bank, bytearray())
        if len(blob) < off + len(data):
            blob.extend(b"\xFF" * (off + len(data) - len(blob)))
        blob[off:off + len(data)] = data
    for bank in sorted(bank_blobs):
        blob = bank_blobs[bank]
        lo = bank * BANK_SIZE
        assert set(card[lo:lo + len(blob)]) == {0xFF}
        card[lo:lo + len(blob)] = blob
        card_written.append((lo, len(blob), f"text pool bank {bank:02X}"))

    # 3) 인덱스 (0x880 홀은 예약 FF 유지 — armchk 는 $1F 단일 사본)
    for lba in SCENES_B9:
        ibank, ioff = where[lba]
        lo = ibank * BANK_SIZE + ioff
        idx = indexes[lba]
        assert set(card[lo:lo + len(idx)]) == {0xFF}
        card[lo:lo + len(idx)] = idx
        card_written.append((lo, len(idx), f"index scene {lba}"))

    CARD_OUT.write_bytes(bytes(card))
    src_ext = CARD_SRC.read_bytes() + b"\xFF" * (CARD_SIZE - 256 * 1024)
    declared = [(lo, lo + ln) for lo, ln, _ in card_written]
    for i, (x, y) in enumerate(zip(src_ext, card)):
        if x != y and not any(s <= i < e for s, e in declared):
            raise ValueError(f"카드 diff 감사 실패 @{i:06X}")

    # 디스어셈블 검산: 로더/리더(디스크) + armchk_v3(카드, 첫 인덱스 뱅크)
    for name, addr, foff, length in (
            ("loader", LOADER, eng_off(LOADER), len(loader)),
            ("reader", wnd_reader_addr, eng_off(wnd_reader_addr), len(reader))):
        r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{addr:X}",
                            f"{foff:X}", f"{length:X}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")
    r = subprocess.run([str(DISASM), "--raw", str(CARD_OUT), f"{ARMCHK_EXEC:X}",
                        f"{ARMCHK_CARD_OFF:X}", f"{len(armchk):X}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"armchk_v3 disasm FAIL:\n{r.stdout}\n{r.stderr}")

    text_total = sum(text_bins)
    manifest = {
        "format": "BTRACK-B9-HOOK-BUILD",
        "runtime_status": "PENDING",
        "changes_vs_b8_3": [
            "card 768KB: 전역 유니크 텍스트 풀($20+) + 씬별 인덱스($41+) 카드"
            " 상주 (RAM 풀·디스크 풀 섹터 전면 폐지)",
            "armchk_v3: 인덱스 base = (SCRATCH+5)<<8 파라미터화,"
            " SCRATCH_KH $AFFE→$C8FD (ROM 쓰기 불가 대응),"
            f" 코드는 기본 카드 $1F:{ARMCHK_CARD_OFF:06X}(논리 $7A00) 단일 사본",
            "리더 v3m: armchk 호출을 MPR3=$1F 브래킷 JSR $7A00 으로",
            "확장 뱅크 $40-$43 스킵 — Arcade Card RAM 창이 카드 ROM 을 가림"
            " (b9 v1 행업/v2 무장실패의 진범, 진단 lua 물리 버스 실측)",
            "54씬 테이블 (행 이미지 = FF + IBANK/IBASE, RUN 무동작)",
            "로더 v4·트랙 확장 무변경"],
        "scenes": {str(lba): {"records": len(payloads[lba]),
                              "index_bank": f"{where[lba][0]:02X}",
                              "index_off": f"{where[lba][1]:04X}",
                              "index_bytes": scene_sizes[lba]}
                   for lba in SCENES_B9},
        "pool": {"unique_records": len(placed), "text_bytes": text_total,
                 "text_banks": n_text_banks,
                 "text_bank_list": [f"{EXT_BANKS[i]:02X}"
                                    for i in range(n_text_banks)],
                 "index_banks": n_idx_banks,
                 "index_bank_list": [f"{EXT_BANKS[n_text_banks + i]:02X}"
                                     for i in range(n_idx_banks)],
                 "arcade_shadow_skipped": "40-43",
                 "spare_banks": len(EXT_BANKS) - n_text_banks - n_idx_banks},
        "armchk_v3_bytes": len(armchk),
        "card": {"out": CARD_OUT.name, "size": len(card),
                 "written_regions": len(card_written)},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader), "free": WINDOW_CODE_END - wnd_end},
        "output_bin_sha256": sha256(out),
        "card_sha256": sha256(card),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK",
                      "scenes": len(SCENES_B9),
                      "records_total": len(all_records),
                      "pool": manifest["pool"],
                      "armchk_v3": len(armchk),
                      "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "sha256": manifest["output_bin_sha256"][:16]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
