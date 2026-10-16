#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B23 — 조사 마커 호출자 게이트(텍스트 프린터 $92F0 복귀일 때만 서브; 스크립트 바이트 오인 행업 수정). 원 b22 설명: 조사 루틴: trail 대기 중 마커 검사 금지(trail $A0-$A3 오인). 원 b21 설명: post 의 A 클로버 수정(조사 루틴이 항상 $1F 를 받던 버그) + 스크래치 초기값 오프셋 수정. 원 b20 설명: b19 에서 PRESENT 게이트 제거(로더가 전투 로드에서 PRESENT=0). 원 b19 설명: b18 + 조사 루틴 v3(모든 바이트 추적·마커 무조건 처리; 배틀 모듈은 $55 비사용). 원 b18 설명:
b17 + **조사(은/는·이/가·을/를·과/와) 런타임 가변 생성**.

근거 (2026-10-09 실측):
- `%s` 핸들러(`$9414`)는 이름을 RAM `$302E` 에 복사하고 zp `$54/$55` 임시 스트림으로 읽는다.
  디스패처(`$4284`)는 임시 스트림 NUL 에서 `$54/$55` 를 지우고 **같은 호출에서 메인 스트림의
  다음 바이트를 반환**한다(Z8.8 ABI). → 템플릿의 `{%s}` 직후 바이트는 이름 끝 호출에서 돌아온다.
- 리더 창(엔진 $84)은 `$55`≠0 이면 native 로 보냈다(v3m). v4 는 그 경우 **창 안에서 `JSR $4284`**
  를 호출한 뒤 조사 루틴(카드 $1F `$79A0`)을 호출한다. 메모 `$53` 스트림은 호출자 MPR6 에
  의존하므로 가드(native 유지).

조사 루틴 (A = 디스패처 반환 바이트, X 보존):
  · `$55`≠0 (이름 진행 중): 마지막 한글 추적 — 1바이트 코드 `$A7-$DD` → LASTHI=$94·LASTLO=코드 /
    2바이트 lead(≥$80) → LASTHI, 다음 바이트 → LASTLO.
  · `$55`=0 (이름 끝 직후): 바이트가 마커 `$1F` 면 다음 바이트(종류 0~3)를 읽고 받침 표
    (뱅크 $5F: `$A000 + (LASTHI-$88)*256 + LASTLO`)로 변형을 골라 **serve 경로**(FLAG/TBANK/CUR)로
    조사 문자열(`$AD00 + idx*8`)을 공급한다. 마커가 아니면 그대로 반환.
인코더: `{%s}` 직후 조사 → `1F` + 종류 (b10 빌더 `B10_JOSA=1`, 길이 동일 4B).

출력: *_btrack_b19.bin/.cue + probes/SystemCard3_btrack_b19.pce
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b9_hook_build as b9
from build_btrack_b7_hook_build import eng_off, FLAG, TBANK, CURL, CURH, PRESENT, SCRATCH, DISASM
import build_btrack_b13_hook_build as b13
Asm = b9.Asm

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b23"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b23.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b23_hook_manifest.json"
CARD_SRC_V3 = ROOT / "probes" / "SystemCard3_btrack_full_v3.pce"
PATCHES = ROOT / "translation" / "btrack_b18_menu_patches.json"
TITLE = ROOT / "translation" / "btrack_title_kr_patches.json"
ONEBYTE = ROOT / "translation" / "b16_onebyte_map.json"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
T2 = b9.T2

# --- 조사 루틴 상수 ---
JOSA_MARK = 0xA0                      # 마커 $A0+종류(0~3) 1바이트. $A0-$A6 은 카타카나 디코더(≥$A7)·히라가나(<$7B) 모두 거부하는
                                      # 값이라 게임 텍스트에 못 나온다. ($1C-$1F 는 메뉴 제어 바이트와 충돌 — 자동 런 실측)
JOSA_BANK = 0x5F                      # 빈 확장 뱅크 (b16 매니페스트 spare)
JOSA_A = 0x799E                       # 카드 $1F 꼬리, 씬 테이블(…0x3F99D) 바로 뒤 = 0x3F99E, armchk(0x3FA00)까지 98B
JOSA_B = 0x7AC3                       # armchk_v5 뒤 (0x3FAC3, 29B 여유)
JOSA_A_CARD = 0x1F * b9.BANK_SIZE + (JOSA_A - 0x6000)
JOSA_B_CARD = 0x1F * b9.BANK_SIZE + (JOSA_B - 0x6000)
LASTHI, LASTLO, EXPECT = 0xC8F2, 0xC8F3, 0xC8F5     # 리더 스크래치 미사용 7B 중
BYTE_TMP = 0xC8F4                                   # post 가 스트림 바이트를 잠시 보관 (MPR3 브래킷이 A 를 덮음)
TBL_HI_BASE = 0xA0 - 0x88             # hi = LASTHI + $18  → $A000 + (lead-$88)*256
ONEBYTE_ROW_HI = 0x94                 # 1바이트 코드 가짜 lead → 표 $AC00
PART_BASE = 0xAD00
JOSA_GATE = 0xAE00                    # (b23) 뱅크 $5F 안 게이트 코드 (받침표 $A000-$ACFF, 조사 $AD00-$AD3F 뒤)
PRINTER_RET = 0x92F0                  # 텍스트 프린터 $92D6 의 `JSR $4036`($92ED) 복귀주소 (PCEHawk 호출자 히스토그램 실측)                    # 조사 문자열 (idx*8)
TYPES = [("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]


READER_V3M_LEN = 86                   # b9 리더 v3m 길이 (post 진입점 = reader + 86)
_ORIG_READER_V3M = b9.asm_reader_v3m  # 몽키패치 전에 원본 보관 (재귀 방지)


def asm_reader_v4(origin: int) -> Asm:
    """v3m 그대로 + 꼬리에 `post` 진입점(트램펄린의 native 읽기 뒤 호출).
    post: A = 디스패처 반환 바이트. MPR3=$1F 브래킷으로 조사 루틴 호출 → C=1 이면 serve 로
    첫 조사 바이트를 $2D80 에 싣고 CLC 복귀, 아니면 그대로 복귀."""
    a = _ORIG_READER_V3M(origin)
    assert len(a.buf) == READER_V3M_LEN, f"reader v3m 길이 변경 {len(a.buf)}"
    a.label("post")
    # (b21) **A 보존**: `TMA #$08` 과 `LDA #$1F` 가 A(스트림 바이트)를 덮어써서 조사 루틴이 항상 $1F 를
    # 받고 있었다 (b18~b20 전부 이 버그 — 실측: LASTLO=1F 고정). 바이트를 $C8F4(미사용 스크래치)에
    # 저장했다가 브래킷 뒤에 복원한다.
    # (b21-2) 트램펄린도 post 호출 전에 `TMA #$40`/`LDA #$84` 로 A 를 덮는다(실측 LASTHI=84). 디스패처는
    # 반환 바이트를 **$2D80** 에도 저장하므로(Z8.8 ABI) post 는 A 를 믿지 않고 $2D80 에서 읽는다.
    a.emit(0x43, 0x08, 0x48)                             # TMA3 PHA
    a.emit(0xA9, 0x1F, 0x53, 0x08)                       # MPR3 = $1F
    a.emit(0xAD, 0x80, 0x2D)                             # LDA $2D80  ← 디스패처 반환 바이트
    a.emit(0x20, JOSA_A & 0xFF, JOSA_A >> 8)             # JSR josa
    a.emit(0x68, 0x53, 0x08)                             # PLA TAM3 (carry 보존)
    a.branch(0xB0, "serve")                              # 무장 → serve (CLC RTS 로 끝남)
    a.label("post_ret")
    a.emit(0x60)                                         # RTS (A/$2D80 = 디스패처 반환)
    return a


def asm_bank81_v3(wnd_slice: int, wnd_reader: int) -> bytes:
    """트램펄린 v3: native 를 `JMP $4284` 꼬리호출 대신 **호출자 MPR6 그대로 `JSR $4284`** 한 뒤
    창의 post 로 후처리(조사). 42B 슬라이스 안(37B)."""
    from build_btrack_b7_hook_build import SLICE_LO, SLICE_HI, TRAMP
    a = Asm(SLICE_LO)
    a.jsr(wnd_slice)
    a.emit(0x80, 0x25)                                   # BRA $6704 (원본과 동일)
    assert a.pc == TRAMP
    a.emit(0x43, 0x40, 0x48)                             # TMA6 PHA
    a.emit(0xA9, 0x84, 0x53, 0x40)                       # MPR6 = $84
    a.jsr(wnd_reader)
    a.emit(0x68, 0x53, 0x40)                             # PLA TAM6 (호출자 MPR6 복원)
    a.branch(0x90, "done")                               # served → done
    a.emit(0x20, 0x84, 0x42)                             # JSR $4284 (native, 호출자 MPR6)
    a.emit(0x43, 0x40, 0x48)                             # TMA6 PHA
    a.emit(0xA9, 0x84, 0x53, 0x40)                       # MPR6 = $84
    a.jsr(wnd_reader + READER_V3M_LEN)                   # JSR post
    a.emit(0x68, 0x53, 0x40)                             # PLA TAM6
    a.label("done")
    a.emit(0xAD, 0x80, 0x2D)                             # LDA $2D80
    a.emit(0x60)                                         # RTS
    code = a.resolve()
    assert len(code) <= SLICE_HI - SLICE_LO, f"bank81_v3 {len(code)}B > 42B"
    return code + b"\xFF" * (SLICE_HI - SLICE_LO - len(code))


def asm_josa_a() -> bytes:
    """post 에서 모든 native 바이트에 대해 호출. A = 바이트.
    ① 마커 $A0-$A3 → 받침 표 조회 → serve 무장(C=1).  ② 그 외: 마지막 한글 추적 —
    lead($80-$9F, $E0+) → LASTHI·EXPECT=1 / EXPECT=1 이면 trail → LASTLO / 1바이트 한글($A7-$DD)
    → LASTHI=$94·LASTLO=코드 / 그 외 단일 바이트(제어·히라가나·$A4-$DF) 무시.
    (v3: 배틀 모듈은 이름을 `$55` 임시 스트림이 아니라 조립된 문자열로 출력하므로 `$55` 의존 제거)"""
    a = Asm(JOSA_A)
    a.emit(0xDA)                                         # PHX
    a.emit(0xAA)                                         # TAX (원 바이트; 비마커 경로는 X 를 끝까지 보존)
    # (b22) trail 대기 중(EXPECT≠0)이면 마커 검사 없이 무조건 trail — 2바이트 한글의 trail 이 $A0-$A3 일 수
    # 있다(「온」=89A0 등 25자). b21 실측: 상태창 「시온」→「시키 お」.
    a.emit(0xAD, EXPECT & 0xFF, EXPECT >> 8)             # LDA EXPECT
    a.branch(0xD0, "trail")
    a.emit(0x8A, 0x29, 0xFC, 0xC9, JOSA_MARK)            # TXA / AND #$FC / CMP #$A0
    a.branch(0xF0, "marker")
    a.emit(0x8A)                                         # TXA
    a.emit(0xC9, 0xA7)
    a.branch(0x90, "chk")
    a.emit(0xC9, 0xDE)
    a.branch(0x90, "one")                                # $A7-$DD → 1바이트 한글
    a.label("chk")
    a.emit(0xC9, 0x80)
    a.branch(0x90, "xit")                                # <$80 단일
    a.emit(0xC9, 0xA0)
    a.branch(0x90, "lead")                               # $80-$9F lead
    a.emit(0xC9, 0xE0)
    a.branch(0x90, "xit")                                # $A0-$DF (마커 제외) 단일
    a.label("lead")                                      # ≥$E0 도 lead
    a.emit(0x8D, LASTHI & 0xFF, LASTHI >> 8)             # STA LASTHI
    a.emit(0xEE, EXPECT & 0xFF, EXPECT >> 8)             # INC EXPECT
    a.branch(0x80, "xit")
    a.label("one")
    a.emit(0xA9, ONEBYTE_ROW_HI)                         # LDA #$94
    a.emit(0x8D, LASTHI & 0xFF, LASTHI >> 8)             # STA LASTHI
    a.label("trail")
    a.emit(0x8A)                                         # TXA (원 바이트)
    a.emit(0x8D, LASTLO & 0xFF, LASTLO >> 8)             # STA LASTLO
    a.emit(0x9C, EXPECT & 0xFF, EXPECT >> 8)             # STZ EXPECT
    a.label("xit")
    a.emit(0xFA, 0x18, 0x60)                             # PLX CLC RTS
    a.label("marker")
    a.emit(0x8A, 0x29, 0x03, 0x0A, 0xAA)                 # TXA AND #3 ASL TAX  (X = 종류*2)
    a.emit(0x43, 0x20, 0x48)                             # TMA5 PHA
    a.emit(0xA9, JOSA_BANK, 0x53, 0x20)                  # MPR5 = $5F
    a.jmp(JOSA_GATE)                                     # (b23) 호출자 게이트 + 받침 조회는 뱅크 $5F 코드
    code = a.resolve()
    assert len(code) <= 98, f"josa A {len(code)}B > 98"
    return code

def asm_josa_gate() -> bytes:
    """(b23) 뱅크 $5F 상주. 마커 경로 진입(MPR5=$5F, 스택: TMA5·X·josa복귀·TMA3·post복귀·TMA6·호출자복귀).
    ① 받침 조회 → idx 를 zp $00 에.  ② **호출자 게이트**: `JSR $4036` 의 복귀주소가 텍스트 프린터
    ($92D6 의 lead 페치 사이트, 복귀 $92F0) 일 때만 서브. 스크립트 인터프리터의 페치(801F/85E5/86xx/8727…
    PCEHawk 실측 — b22 교회 장면 전환 바이트 $A0-$A3 가 「를」로 서브되어 행업)는 무시(C=0, 바이트 그대로)."""
    a = Asm(JOSA_GATE)
    a.emit(0xAD, LASTHI & 0xFF, LASTHI >> 8)
    a.emit(0x18, 0x69, TBL_HI_BASE)                      # CLC ADC #$18
    a.emit(0x85, 0x01)                                   # STA $01
    a.emit(0xAD, LASTLO & 0xFF, LASTLO >> 8)
    a.emit(0x85, 0x00)                                   # STA $00
    a.emit(0xB2, 0x00)                                   # LDA ($00) = 받침(0/1)
    a.emit(0x29, 0x01)                                   # AND #1
    a.emit(0x85, 0x00, 0x8A, 0x05, 0x00, 0x85, 0x00)     # STA $00 / TXA / ORA $00 / STA $00  → $00 = idx
    a.emit(0xBA)                                         # TSX
    a.emit(0xBD, 0x09, 0x21)                             # LDA $2109,X  (호출자 복귀 lo)
    a.emit(0xC9, PRINTER_RET & 0xFF)
    a.branch(0xD0, "no")
    a.emit(0xBD, 0x0A, 0x21)                             # LDA $210A,X  (hi)
    a.emit(0xC9, PRINTER_RET >> 8)
    a.branch(0xD0, "no")
    a.emit(0xA5, 0x00)                                   # LDA $00 (idx)
    a.jmp(JOSA_B)
    a.label("no")
    a.emit(0x68, 0x53, 0x20)                             # PLA TAM5
    a.emit(0xFA, 0x18, 0x60)                             # PLX CLC RTS
    return a.resolve()


def asm_josa_b() -> bytes:
    a = Asm(JOSA_B)
    a.emit(0x0A, 0x0A, 0x0A)                             # ×8
    a.emit(0x8D, CURL & 0xFF, CURL >> 8)                 # STA CURL
    a.emit(0xA9, PART_BASE >> 8, 0x8D, CURH & 0xFF, CURH >> 8)
    a.emit(0xA9, JOSA_BANK, 0x8D, TBANK & 0xFF, TBANK >> 8)
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)
    a.emit(0x68, 0x53, 0x20)                             # PLA TAM5
    a.emit(0xFA, 0x38, 0x60)                             # PLX SEC RTS
    code = a.resolve()
    assert len(code) <= 29, f"josa B {len(code)}B > 29"
    return code


def josa_bank_image() -> bytes:
    asg = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    omap = json.loads(ONEBYTE.read_text(encoding="utf-8"))["map"]
    img = bytearray(b"\xFF" * b9.BANK_SIZE)
    # 받침 표: lead $88..$93 → 행 0..11, $94 → 1바이트 코드 행
    def batchim(ch): return 1 if (ord(ch) - 0xAC00) % 28 else 0
    for i in range(13 * 256):
        img[i] = 0
    for ch, e in asg.items():
        lead, trail = int(e["sjis"][:2], 16), int(e["sjis"][2:], 16)
        assert 0x88 <= lead <= 0x93, f"예상 밖 lead {e['sjis']}"
        img[(lead - 0x88) * 256 + trail] = batchim(ch)
    for code, v in omap.items():
        img[(ONEBYTE_ROW_HI - 0x88) * 256 + int(code, 16)] = batchim(v["ch"])
    # 조사 문자열 (2바이트 배정 코드 + NUL), idx = 종류*2 + 받침
    base = PART_BASE - 0xA000
    for t, (yes, no) in enumerate(TYPES):
        for b, p in ((1, yes), (0, no)):
            enc = b"".join(bytes.fromhex(asg[c]["sjis"]) for c in p) + b"\x00"
            off = base + (t * 2 + b) * 8
            img[off:off + len(enc)] = enc
            img[off + len(enc):off + 8] = b"\x00" * (8 - len(enc))
    g = asm_josa_gate(); img[JOSA_GATE - 0xA000:JOSA_GATE - 0xA000 + len(g)] = g
    return bytes(img)


def main() -> None:
    b9.OUT_BIN = OUT_BIN
    b9.OUT_CUE = OUT_CUE
    b9.CARD_OUT = CARD_OUT
    b9.OUT_MANIFEST = ROOT / "translation" / "btrack_b23_b9stage_manifest.json"
    b9.CARD_SRC = CARD_SRC_V3
    b9.ARMCHK_BUILDER = b13.asm_armchk_v5
    b9.asm_reader_v3m = asm_reader_v4                    # ← 리더 v3m + post
    b9.asm_bank81 = asm_bank81_v3                        # ← 트램펄린 v3 (native 를 JSR 로)
    b9.main()

    josa_a, josa_b = asm_josa_a(), asm_josa_b()
    # --- 디스크: b16 메뉴 패치(b18 재생성본) + 카타카나 테이블 + 타이틀 셀 + 스크래치 초기값 ---
    doc = json.loads(PATCHES.read_text(encoding="utf-8"))
    out = bytearray(OUT_BIN.read_bytes())
    total = 0
    for p in doc["patches"]:
        off = T2 + p["iso_off"]
        old = bytes.fromhex(p["old_hex"]); new = bytes.fromhex(p["new_hex"])
        assert len(old) == len(new)
        if bytes(out[off:off + len(old)]) != old:
            raise ValueError(f"패치 전제 불일치 @iso {p['iso_off']:07X}")
        out[off:off + len(new)] = new
        total += len(new)
    omap = json.loads(ONEBYTE.read_text(encoding="utf-8"))["map"]
    orig_tbl = bytes(out[T2 + 0x86104:T2 + 0x86104 + 110])
    assert orig_tbl[:6] == bytes.fromhex("834083428344")
    new_tbl = bytearray(orig_tbl)
    for code, v in omap.items():
        i = int(code, 16) - 0xA7
        new_tbl[2 * i:2 * i + 2] = bytes.fromhex(v["sjis"])
    for iso_off in (0x86104, 0x453D0):
        off = T2 + iso_off
        assert bytes(out[off:off + 110]) == orig_tbl, f"카타카나 테이블 원본 불일치 @iso {iso_off:07X}"
        out[off:off + 110] = new_tbl
    tdoc = json.loads(TITLE.read_text(encoding="utf-8"))
    for p in tdoc["patches"]:
        off = T2 + p["iso_off"]
        old_b = bytes.fromhex(p["old_hex"]); new_b = bytes.fromhex(p["new_hex"])
        if bytes(out[off:off + 128]) != old_b:
            raise ValueError(f"타이틀 셀 원본 불일치 @iso {p['iso_off']:07X}")
        out[off:off + 128] = new_b
    # 스크래치 초기값 (엔진 $84 이미지): LASTHI=$94 LASTLO=00 ($AC00 = 0) KIND(미사용)=00 EXPECT=00
    # 엔진 이미지의 $C8C8..$C8FF 는 디스크상 데이터 바이트지만 런타임 미사용 스크래치
    # (b7 이래 FLAG 영역 "state=0" 패치와 같은 전제, b11 PTRL_V4 도 $C8F2-4 사용).
    so = eng_off(LASTHI)          # eng_off 는 이미 bin 오프셋(T2 포함) — T2 를 더하면 씬 4130 패키지를 오염시킨다(2026-10-09 사고)
    out[so:so + 4] = bytes((0x00, 0x00, 0x00, 0x00))          # LASTHI=0: 부팅 직후 마커 오인 방지
    OUT_BIN.write_bytes(bytes(out))

    # --- 카드: 조사 코드 2조각 + 데이터 뱅크 $5F ---
    card = bytearray(CARD_OUT.read_bytes())
    for off, code, name in ((JOSA_A_CARD, josa_a, "josa A"), (JOSA_B_CARD, josa_b, "josa B")):
        assert set(card[off:off + len(code)]) == {0xFF}, f"{name} 자리 비어 있지 않음 @{off:06X}"
        card[off:off + len(code)] = code
    lo = JOSA_BANK * b9.BANK_SIZE
    assert set(card[lo:lo + b9.BANK_SIZE]) == {0xFF}, "JOSA 뱅크가 비어 있지 않음"
    card[lo:lo + b9.BANK_SIZE] = josa_bank_image()
    CARD_OUT.write_bytes(bytes(card))
    for name, addr, foff, length in (("josa A", JOSA_A, JOSA_A_CARD, len(josa_a)),
                                     ("josa B", JOSA_B, JOSA_B_CARD, len(josa_b))):
        r = subprocess.run([str(DISASM), "--raw", str(CARD_OUT), f"{addr:X}", f"{foff:X}", f"{length:X}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B23-HOOK-BUILD", "runtime_status": "PENDING",
        "base": "b17 + 리더 v4($55 창 내 처리) + 조사 루틴(카드 $1F $79A0/$7AC3) + 뱅크 $5F 받침표",
        "josa": {"mark": JOSA_MARK, "bank": JOSA_BANK, "code_a": {"addr": JOSA_A, "bytes": len(josa_a), "hex": josa_a.hex()}, "gate": {"addr": JOSA_GATE, "bytes": len(asm_josa_gate()), "hex": asm_josa_gate().hex(), "printer_ret": PRINTER_RET},
                 "code_b": {"addr": JOSA_B, "bytes": len(josa_b), "hex": josa_b.hex()},
                 "scratch": {"LASTHI": LASTHI, "LASTLO": LASTLO, "EXPECT": EXPECT}, "types": TYPES},
        "menu_stage": {"patches": len(doc["patches"]), "patched_bytes": total},
        "title_logo": {"cells_patched": len(tdoc["patches"])},
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK", "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "josa_a": len(josa_a), "josa_b": len(josa_b), "menu_patches": len(doc["patches"])},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
