#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B8 — 58씬 롤아웃 인프라 (로더 v4 + ARMCHK 이동 + 트랙 확장).

b7.6 대비 변경 (2026-08-23 설계 — 씬은 3개 그대로, 인프라만 교체):
  1. **로더 v4**: 카드 씬 테이블 워크를 절대,Y(8bit, 5씬 한계)에서
     zp 포인터 ($00/$01 저장·복원, (zp),Y) 워크로 교체 — 씬 수 한계는
     폰트 꼬리 용량(2,701B ÷ 44B = 61씬)뿐. 매치 시 42B 복사는 동일.
  2. **ARMCHK $A780 → $A880 (INDEX_CAP 0x780 → 0x880)**: 대형 씬 인덱스
     (3842 = 2,069B, 3362 = 1,985B)를 수용. 리더 JSR 갱신 + 전 씬 인덱스
     뱅크 이미지 재배치 (텍스트 용량 합계는 불변).
  3. **트랙 확장 +1024섹터** (V19_track_ext 로 부팅·BGM 실증된 변환 재현):
     트랙2 데이터 끝(파일 프레임 12693)에 1024×2048B 00 삽입 + cue 트랙3+
     INDEX MSF 를 +1024 프레임 시프트. CD-DA 는 BCD 트랙번호 호출이라 안전
     (§6 Z9 실측). 확장 영역(트랙2-상대 12693..13716)은 이후 씬 풀 배치처.

씬 페이로드·풀 배치는 b7.6 과 동일 (482/290 균일 + 2882 카드 하이브리드,
풀 base 9178/9192/9206 — 전부 삽입 지점 앞이라 오프셋 불변).
게이트: 기존 강화 코스 회귀 + BGM/ADPCM 전 코스 (트랙 확장 영향 확인).

출력: *_btrack_b8.bin/.cue + probes/SystemCard3_btrack_b8.pce
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_hook_build import (      # 무변경 재사용분
    Asm, make_slice, asm_bank81, scene_rows_image, st_abs, ld_abs,
    T2, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP, WINDOW_LO, LOADER,
    SCRATCH, RESTORE_OFF, WINDOW_CODE_END, FLAG, TBANK, CURL, CURH,
    PRESENT, WINDOW_HI, TEXT_SECTORS, INDEX_BANK, INDEX_SECTORS,
    ROWS_IMG_LEN, ENTRY_LEN, BANK_SIZE, INDEX_MAGIC, TRAP, SCRATCH_KH,
    CARD_TABLE_OFF, CARD_BANK, CARD_TABLE_LOGICAL,
    SRC_BIN, SRC_SHA256, SRC_CUE, CARD_SRC, DISASM,
)
from build_btrack_b7_6_hook_build import (
    HY_LBA, HY_BASE, HY_SECTORS, HY_BANK_IDX, HY_BANK_TXT,
    CARD_TEXT_BINS, FONT_TAIL, hybrid_rows_image,
)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b8_1"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b8_1.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b8_1_hook_manifest.json"
ASSET_MAP = ROOT / "module_relink" / "z9_static_asset_map" / "manifest.json"

# 균일 씬 (lba, pool_base, 텍스트 뱅크 — 개수 가변, 인덱스 = INDEX_BANK).
# b8.1 (2026-08-23 밤): 290 을 $76/$7F 로 재선정 — seg_290_town2 실측으로
# 구 뱅크 $78/$79/$7A 가 두 번째 마을에서 소비됨이 판명 (정적 지도 후보
# {76,7E,7F}). 채택 뱅크 ⊆ 정적 지도 후보를 main() 에서 강제 검증한다.
SCENES_UNIFORM = [(482, 9178, [0x7B, 0x7C, 0x7D]),
                  (290, 9192, [0x76, 0x7F])]


def uniform_rows_image(lba: int, base: int, tbanks: list[int]) -> bytes:
    """가변 뱅크 수 균일 씬의 SCRATCH 행 이미지 42B
    (b7 scene_rows_image 의 TEXT_SECTORS=12 고정 가정 제거)."""
    def row(l, cnt, bank):
        return bytes(((l >> 16) & 0xFF, (l >> 8) & 0xFF, l & 0xFF, cnt, bank))
    def rowset(rows):
        img = bytearray()
        for r in rows:
            img += row(*r)
        img.append(0xFF)
        assert len(img) <= ROWS_IMG_LEN
        img.extend(b"\xFF" * (ROWS_IMG_LEN - len(img)))
        return bytes(img)
    pool = rowset([(base + i * 4, 4, b) for i, b in enumerate(tbanks)]
                  + [(base + 4 * len(tbanks), INDEX_SECTORS, INDEX_BANK)])
    restore = rowset([(lba + (b - 0x68) * 4, 4, b) for b in tbanks]
                     + [(lba + (INDEX_BANK - 0x68) * 4, INDEX_SECTORS,
                         INDEX_BANK)])
    return pool + restore

# ---- b8 상수 (b7 대비 변경) --------------------------------------------------
ARMCHK = 0xA880                      # ← $A780 에서 이동
INDEX_CAP = 0x880                    # ← 0x780 에서 확대 (최대 인덱스 2,069B)
EXT_SECTORS = 1024                   # V19 실증 확장량
DATA_FRAMES = 12693                  # 트랙2 데이터 원본 프레임 수 (§6)
INS_OFF = T2 + DATA_FRAMES * 2048    # BIN 삽입 지점
SECTOR = 2048


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


# ---- 로더 v4 (zp 포인터 테이블 워크) -----------------------------------------

def asm_loader_v4() -> Asm:
    """v3 과 동일 의미론, 테이블 워크만 zp 포인터로 일반화.
    zp $00/$01 은 저장·복원 (로더 컨텍스트 liveness 미확정 — fail-closed)."""
    a = Asm(LOADER)
    a.emit(0xA5, 0xFF, 0xC9, 0x06)                 # LDA $FF CMP #$06
    a.branch(0xD0, "tail")
    a.emit(0x5A)                                   # PHY
    a.emit(0xA5, 0x00, 0x48, 0xA5, 0x01, 0x48)     # zp $00/$01 저장
    a.emit(0x43, 0x20, 0x48)                       # TMA #$20 PHA
    a.emit(0xA9, CARD_BANK, 0x53, 0x20)            # 카드 매핑
    a.emit(0xA9, CARD_TABLE_LOGICAL & 0xFF, 0x85, 0x00)
    a.emit(0xA9, CARD_TABLE_LOGICAL >> 8, 0x85, 0x01)
    a.label("loop")
    a.emit(0xA0, 0x00)                             # LDY #0
    a.emit(0xB1, 0x00)                             # LDA ($00),Y — lba mid
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "wnomatch")
    a.emit(0xC5, 0xFD)                             # CMP $FD
    a.branch(0xD0, "next")
    a.emit(0xC8, 0xB1, 0x00)                       # INY LDA ($00),Y — lba lo
    a.emit(0xC5, 0xFE)                             # CMP $FE
    a.branch(0xD0, "next")
    # match: 행 이미지 42B 를 SCRATCH 로 복사
    a.emit(0xDA)                                   # PHX
    a.emit(0xA2, 0x00, 0xA0, 0x02)                 # LDX #0 LDY #2
    a.label("cpy")
    a.emit(0xB1, 0x00)                             # LDA ($00),Y
    a.emit(0x9D, SCRATCH & 0xFF, SCRATCH >> 8)     # STA SCRATCH,X
    a.emit(0xC8, 0xE8, 0xE0, ROWS_IMG_LEN * 2)     # INY INX CPX #42
    a.branch(0xD0, "cpy")
    a.emit(0xFA)                                   # PLX
    a.emit(0x38)                                   # SEC = match
    a.branch(0x80, "unwind")
    a.label("next")
    a.emit(0x18, 0xA5, 0x00, 0x69, ENTRY_LEN, 0x85, 0x00)  # ptr += 44
    a.branch(0x90, "loop")
    a.emit(0xE6, 0x01)                             # INC $01
    a.branch(0x80, "loop")
    a.label("wnomatch")
    a.emit(0x18)                                   # CLC = nomatch
    a.label("unwind")
    a.emit(0x68, 0x53, 0x20)                       # PLA TAM#$20 (카드 복원)
    a.emit(0x68, 0x85, 0x01, 0x68, 0x85, 0x00)     # zp 복원 (역순)
    a.emit(0x7A)                                   # PLY
    a.branch(0xB0, "match")
    # ---- 비매치: PRESENT=1 → 복원 행 RUN(21) ----
    ld_abs(a, PRESENT)
    a.branch(0xF0, "tail")
    a.emit(0xA9, RESTORE_OFF)
    a.jsr("run")
    a.emit(0x9C, PRESENT & 0xFF, PRESENT >> 8)
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
    # ---- RUN (b7 v3.1 과 동일) ----
    a.label("run")
    a.emit(0x08, 0x48, 0xDA, 0x5A)
    a.emit(0xAA)
    a.emit(0xA0, 0x00)
    a.label("zsave")
    a.emit(0xB9, 0xF8, 0x20)
    a.emit(0x48)
    a.emit(0xC8, 0xC0, 0x08)
    a.branch(0xD0, "zsave")
    a.label("rloop")
    a.emit(0xBD, SCRATCH & 0xFF, SCRATCH >> 8)
    a.emit(0xC9, 0xFF)
    a.branch(0xF0, "endrun")
    a.emit(0x85, 0xFC)
    for off, zp in ((1, 0xFD), (2, 0xFE), (3, 0xF8), (4, 0xFA)):
        a.emit(0xBD, (SCRATCH + off) & 0xFF, (SCRATCH + off) >> 8)
        a.emit(0x85, zp)
    a.emit(0x64, 0xF9, 0x64, 0xFB)
    a.emit(0xA9, 0x06, 0x85, 0xFF)
    a.emit(0xDA, 0x20, 0x09, 0xE0, 0xFA)
    a.emit(0x8A, 0x18, 0x69, 0x05, 0xAA)
    a.branch(0x80, "rloop")
    a.label("endrun")
    a.emit(0xA0, 0x07)
    a.label("zrest")
    a.emit(0x68)
    a.emit(0x99, 0xF8, 0x20)
    a.emit(0x88)
    a.branch(0x10, "zrest")
    a.emit(0x7A, 0xFA, 0x68, 0x28)
    a.emit(0x60)
    return a


# ---- 리더/armchk (b7 사본 — ARMCHK/INDEX_CAP 만 b8 상수) ---------------------

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


# ---- 패킹 (b7/b7.6 사본 — INDEX_CAP/ARMCHK 만 b8 상수) -----------------------

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

    text_img = bytearray()
    for b in text_banks:
        seg = bytearray(banks[b])
        while len(seg) < BANK_SIZE:
            seg.extend(TRAP)
        text_img.extend(seg[:BANK_SIZE])
    idx_img = bytearray(index)
    idx_img.extend(b"\x00" * (INDEX_CAP - len(index)))
    idx_img.extend(armchk)
    assert INDEX_CAP + len(armchk) <= 0xFFE
    while len(idx_img) < INDEX_SECTORS * 2048:
        idx_img.extend(TRAP)
    return bytes(text_img), bytes(idx_img[:INDEX_SECTORS * 2048]), \
        {f"{b:02X}": len(banks[b]) for b in text_banks}, len(index)


def pack_hybrid(records, armchk: bytes, card: bytes):
    n = len(records)
    index_len = 2 + 48 + 7 * n + 24
    if index_len > INDEX_CAP:
        raise ValueError(f"인덱스 {index_len}B > {INDEX_CAP:#x}")
    armchk_end = INDEX_CAP + len(armchk)

    bins = [
        ("ram7F", "ram", HY_BANK_TXT, 0, BANK_SIZE),
        ("ram7E_hi", "ram", HY_BANK_IDX, armchk_end, BANK_SIZE - armchk_end),
        ("ram7E_lo", "ram", HY_BANK_IDX, index_len, INDEX_CAP - index_len),
    ] + [
        (f"card_{s:05X}", "card", s // BANK_SIZE, s & (BANK_SIZE - 1), e - s)
        for s, e in CARD_TEXT_BINS
    ]
    for name, kind, bank, off, cap in bins:
        if kind == "card":
            lo = bank * BANK_SIZE + off
            if set(card[lo:lo + cap]) != {0xFF}:
                raise ValueError(f"{name}: 카드 구간이 FF 아님")
            fs, fe = FONT_TAIL
            if max(lo, fs) < min(lo + cap, fe):
                raise ValueError(f"{name}: 폰트 꼬리 예약 구간 침범")

    cursors = {b[0]: 0 for b in bins}
    placed = {}
    for r in sorted(records, key=lambda r: -len(r["encoded_hex"])):
        data = bytes.fromhex(r["encoded_hex"])
        if 0 in data[:-1]:
            raise ValueError(f"{r['id']}: 내부 00")
        for name, kind, bank, off, cap in bins:
            if cursors[name] + len(data) <= cap:
                placed[r["id"]] = (name, cursors[name])
                cursors[name] += len(data)
                break
        else:
            raise ValueError(f"{r['id']}: 배치 공간 부족 ({len(data)}B)")

    bin_by_name = {b[0]: b for b in bins}

    def locate(rid):
        name, o = placed[rid]
        _, kind, bank, off, _ = bin_by_name[name]
        return bank, 0xA000 + off + o

    buckets = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, addr = locate(r["id"])
        buckets[kb].append(((off13 >> 8) & 0x1F, off13 & 0xFF, bank,
                            addr, r["original_raw_length"]))
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
    assert len(index) == index_len, (len(index), index_len)

    img7e = bytearray(b"\x00" * BANK_SIZE)
    img7e[0:len(index)] = index
    img7e[INDEX_CAP:armchk_end] = armchk
    img7f = bytearray(TRAP * (BANK_SIZE // 2))
    card_patches = {}
    for r in records:
        data = bytes.fromhex(r["encoded_hex"])
        name, o = placed[r["id"]]
        _, kind, bank, off, _ = bin_by_name[name]
        if name == "ram7F":
            img7f[o:o + len(data)] = data
        elif kind == "ram":
            img7e[off + o:off + o + len(data)] = data
        else:
            card_patches.setdefault(name, {})[o] = data
    for name, kind, bank, off, cap in bins:
        if kind == "ram" and bank == HY_BANK_IDX:
            used = cursors[name]
            pad = bytearray(TRAP * ((cap - used) // 2 + 1))[:cap - used]
            img7e[off + used:off + cap] = pad

    card_out = []
    for name, kind, bank, off, cap in bins:
        if kind != "card" or name not in card_patches:
            continue
        lo = bank * BANK_SIZE + off
        blob = bytearray(b"\xFF" * cursors[name])
        for o, data in card_patches[name].items():
            blob[o:o + len(data)] = data
        card_out.append((lo, bytes(blob), name))

    stats = {name: {"capacity": cap, "used": cursors[name],
                    "kind": kind, "bank": f"{bank:02X}"}
             for name, kind, bank, off, cap in bins}
    return bytes(img7e), bytes(img7f), card_out, stats, index_len


# ---- cue 확장 ----------------------------------------------------------------

def shift_cue(src_text: str, bin_name: str, add_frames: int) -> str:
    out = []
    track = 0
    for line in src_text.splitlines():
        s = line.strip()
        if s.startswith("FILE"):
            line = f'FILE "{bin_name}" BINARY'
        elif s.startswith("TRACK"):
            track = int(s.split()[1])
        elif s.startswith("INDEX") and track >= 3:
            tag, num, msf = s.split()
            mm, ss, ff = (int(x) for x in msf.split(":"))
            fr = (mm * 60 + ss) * 75 + ff + add_frames
            mm, r = divmod(fr, 60 * 75)
            ss, ff = divmod(r, 75)
            line = f"    INDEX {num} {mm:02d}:{ss:02d}:{ff:02d}"
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 사전검증 (b7.6 동일)
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42))
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65))
    assert slice_src[-2:] == bytes((0xD0, 0xD6))
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창 오염"
    for lba, base, tbanks in SCENES_UNIFORM:
        nsec = 4 * len(tbanks) + INDEX_SECTORS
        seg = bytes(out[T2 + base * 2048: T2 + (base + nsec) * 2048])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"
    seg = bytes(out[T2 + HY_BASE * 2048: T2 + (HY_BASE + HY_SECTORS) * 2048])
    assert set(seg) == {0}, f"풀 base {HY_BASE}: 원본 00-fill 아님"
    # 채택 뱅크 ⊆ 정적 자산 지도 후보 (fail-closed 가드 — town2 사례 재발 방지)
    amap = json.loads(ASSET_MAP.read_text(encoding="utf-8"))
    for lba, base, tbanks in SCENES_UNIFORM:
        cand = set(amap["scene_verdicts"][str(lba)]["candidate_banks"])
        chosen = {f"{b:02X}" for b in tbanks} | {f"{INDEX_BANK:02X}"}
        if not chosen <= cand:
            raise ValueError(
                f"scene {lba}: 채택 뱅크 {sorted(chosen)} ⊄ 후보 {sorted(cand)}")
    cand = set(amap["scene_verdicts"][str(HY_LBA)]["candidate_banks"])
    assert {f"{HY_BANK_IDX:02X}", f"{HY_BANK_TXT:02X}"} <= cand
    # 씬 테이블 용량 (v4: Y 한계 없음, 폰트 꼬리가 상한)
    n_scenes = len(SCENES_UNIFORM) + 1
    assert n_scenes * ENTRY_LEN + 1 <= FONT_TAIL[1] - FONT_TAIL[0], "테이블 > 폰트 꼬리"

    # 창 조립
    loader = asm_loader_v4().resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > WINDOW_CODE_END:
        raise ValueError(f"창 코드 초과: {wnd_end:#06x} > {WINDOW_CODE_END:#06x}")
    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)
    armchk = asm_armchk()

    # 씬 풀
    scene_stats = {}
    pool_patches = []
    for lba, base, tbanks in SCENES_UNIFORM:
        pl = json.loads((ROOT / "translation" /
                         (f"btrack_b7_scene_{lba}_payload.json"
                          if lba != 482 else "btrack_b4_field_payload.json")
                         ).read_text(encoding="utf-8"))["records"]
        text_img, idx_img, tstats, ilen = pack_scene(pl, armchk, tbanks)
        pool_patches.append((T2 + base * 2048, text_img, f"scene {lba} text"))
        pool_patches.append((T2 + (base + 4 * len(tbanks)) * 2048, idx_img,
                             f"scene {lba} index"))
        scene_stats[str(lba)] = {"records": len(pl), "text": tstats,
                                 "index_bytes": ilen, "pool_base": base,
                                 "mode": "uniform",
                                 "text_banks": [f"{b:02X}" for b in tbanks]}
    card = bytearray(CARD_SRC.read_bytes())
    pl2882 = json.loads((ROOT / "translation" /
                         f"btrack_b7_scene_{HY_LBA}_payload.json"
                         ).read_text(encoding="utf-8"))["records"]
    img7e, img7f, card_text, hstats, hy_index_len = \
        pack_hybrid(pl2882, armchk, bytes(card))
    pool_patches.append((T2 + HY_BASE * 2048, img7e + img7f,
                         f"scene {HY_LBA} hybrid pool"))
    scene_stats[str(HY_LBA)] = {
        "records": len(pl2882), "mode": "hybrid", "pool_base": HY_BASE,
        "index_bytes": hy_index_len, "bins": hstats,
        "text_total": sum(len(r["encoded_hex"]) // 2 for r in pl2882)}

    # 패치 적용 → 트랙 확장 삽입 (전 패치가 삽입 지점 앞임을 확인)
    patches = [(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8)), "vector"),
               (eng_off(SLICE_LO), bank81, "bank81"),
               (eng_off(WINDOW_LO), loader + wslice + reader, "window code"),
               (eng_off(FLAG), bytes(6), "state=0")] + pool_patches
    for off, data, _ in patches:
        assert off + len(data) <= INS_OFF, "패치가 삽입 지점을 넘음"
        out[off:off + len(data)] = data
    out[INS_OFF:INS_OFF] = bytes(EXT_SECTORS * 2048)
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(shift_cue(SRC_CUE.read_text(encoding="ascii"),
                                 OUT_BIN.name, EXT_SECTORS), encoding="ascii")

    # 카드
    table = bytearray()
    for lba, base, tbanks in SCENES_UNIFORM:
        table.extend(((lba >> 8) & 0xFF, lba & 0xFF))
        table.extend(uniform_rows_image(lba, base, tbanks))
    table.extend(((HY_LBA >> 8) & 0xFF, HY_LBA & 0xFF))
    table.extend(hybrid_rows_image())
    table.append(0xFF)
    assert set(card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)]) == {0xFF}
    card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)] = table
    card_written = [(CARD_TABLE_OFF, len(table), "scene table")]
    for lo, blob, name in card_text:
        assert set(card[lo:lo + len(blob)]) == {0xFF}, f"{name}: FF 아님"
        card[lo:lo + len(blob)] = blob
        card_written.append((lo, len(blob), name))
    CARD_OUT.write_bytes(bytes(card))
    src_card = CARD_SRC.read_bytes()
    declared = [(lo, lo + ln) for lo, ln, _ in card_written]
    for i, (x, y) in enumerate(zip(src_card, card)):
        if x != y and not any(s <= i < e for s, e in declared):
            raise ValueError(f"카드 diff 감사 실패 @{i:06X}")

    # 디스어셈블 검산: 로더 v4 + 리더 (JSR $A880 변경분)
    for name, addr, length in (("loader", LOADER, len(loader)),
                               ("reader", wnd_reader_addr, len(reader))):
        r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{addr:X}",
                            f"{eng_off(addr):X}", f"{length:X}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B8-HOOK-BUILD",
        "runtime_status": "PENDING",
        "changes_vs_b7_6": ["loader v4 (zp-pointer table walk, no 5-scene limit)",
                            f"ARMCHK -> {ARMCHK:#x}, INDEX_CAP -> {INDEX_CAP:#x}",
                            f"track extension +{EXT_SECTORS} sectors (V19-proven)",
                            "b8.1: scene 290 text banks -> $76/$7F "
                            "(seg_290_town2 실측 — 구 $78/$79/$7A 는 둘째 마을 소비)"],
        "scenes": scene_stats,
        "card": {"out": CARD_OUT.name,
                 "written": [{"off": f"{lo:06X}", "bytes": ln, "what": w}
                             for lo, ln, w in card_written]},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader), "free": WINDOW_CODE_END - wnd_end},
        "extension": {"insert_off": INS_OFF, "sectors": EXT_SECTORS,
                      "new_data_frames": DATA_FRAMES + EXT_SECTORS},
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
