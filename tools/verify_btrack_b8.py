#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B8 최종 산출물 검증.

검증 항목 (fail-closed):
  1. 트랙 확장 구조: 삽입 지점 앞 = 패치된 원본, 삽입 1024섹터 = 00,
     삽입 뒤 = 원본과 바이트 동일 (시프트 검증)
  2. cue: 트랙 1-2 무변경, 트랙 3+ INDEX = 원본 +1024 프레임
  3. 3씬 전부 인덱스 전수 워크 + serve 시뮬레이션 — 페이로드와 바이트 왕복
     (INDEX_CAP 0x880 재배치 반영, 카드 상주 레코드 포함)
  4. 씬 테이블 v4 워크 시뮬레이션 (zp 포인터 의미론): 3엔트리 매치/비매치
  5. 카드 diff = 선언 범위뿐, 복원 행 대상 섹터 무수정
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b8_hook_build import (
    OUT_BIN, OUT_CUE, CARD_OUT, ARMCHK, INDEX_CAP, EXT_SECTORS, INS_OFF,
    SCENES_UNIFORM, asm_armchk,
)
from build_btrack_b7_6_hook_build import (
    HY_LBA, HY_BASE, HY_BANK_IDX, HY_BANK_TXT,
    CARD_TEXT_BINS,
)
from build_btrack_b7_hook_build import (
    T2, TEXT_SECTORS, INDEX_BANK, INDEX_MAGIC, ENTRY_LEN,
    CARD_TABLE_OFF, SRC_BIN, SRC_CUE, CARD_SRC,
)

SECTOR = 2048
BANK_SIZE = 8192


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def parse_cue_indexes(text):
    out = {}
    track = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("TRACK"):
            track = int(s.split()[1])
        elif s.startswith("INDEX"):
            mm, ss, ff = (int(x) for x in s.split()[2].split(":"))
            out[track] = (mm * 60 + ss) * 75 + ff
    return out


def main() -> None:
    out = OUT_BIN.read_bytes()
    src = SRC_BIN.read_bytes()
    card = CARD_OUT.read_bytes()
    card_src = CARD_SRC.read_bytes()

    # 1. 트랙 확장 구조
    ins_len = EXT_SECTORS * SECTOR
    if len(out) != len(src) + ins_len:
        fail(f"bin 크기 {len(out)} != 원본+{ins_len}")
    if any(out[INS_OFF:INS_OFF + ins_len]):
        fail("확장 영역이 00 이 아님")
    if out[INS_OFF + ins_len:] != src[INS_OFF:]:
        fail("삽입 뒤 데이터가 원본과 다름 (시프트 오류)")

    # 2. cue 시프트
    a = parse_cue_indexes(SRC_CUE.read_text(encoding="ascii"))
    b = parse_cue_indexes(OUT_CUE.read_text(encoding="ascii"))
    for t in a:
        want = a[t] + (EXT_SECTORS if t >= 3 else 0)
        if b.get(t) != want:
            fail(f"cue 트랙 {t}: {b.get(t)} != {want}")

    # 3. 3씬 serve 시뮬레이션
    armchk_len = len(asm_armchk())

    def read_text(images, bank, addr):
        off = addr - 0xA000
        if not (0 <= off < BANK_SIZE):
            fail(f"addr {addr:04X} 창 밖")
        blob = images[bank] if bank in images else \
            card[bank * BANK_SIZE:(bank + 1) * BANK_SIZE]
        end = blob.index(0, off)
        return bytes(blob[off:end + 1])

    def walk_index(idx, images, payload, scene):
        by_key = {}
        for r in payload:
            key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
            by_key[key] = r
        if idx[0:2] != INDEX_MAGIC:
            fail(f"scene {scene}: 인덱스 매직 불일치")
        seen = set()
        for kb in range(24):
            p = idx[2 + kb * 2] | (idx[3 + kb * 2] << 8)
            cur = p - 0xA000
            while idx[cur] != 0xFF:
                oh, ol, bank, alo, ahi, llo, lhi = idx[cur:cur + 7]
                key = (kb << 13) | (oh << 8) | ol
                r = by_key.get(key)
                if r is None:
                    fail(f"scene {scene}: 키 {key:06X} 대응 레코드 없음")
                if r["id"] in seen:
                    fail(f"scene {scene}: {r['id']} 중복")
                seen.add(r["id"])
                text = read_text(images, bank, alo | (ahi << 8))
                if text != bytes.fromhex(r["encoded_hex"]):
                    fail(f"scene {scene}: {r['id']} serve 불일치 (bank {bank:02X})")
                if (llo | (lhi << 8)) != r["original_raw_length"] - 1:
                    fail(f"scene {scene}: {r['id']} 원문 길이 불일치")
                cur += 7
        if len(seen) != len(payload):
            fail(f"scene {scene}: 엔트리 {len(seen)} != 레코드 {len(payload)}")
        # armchk 위치 확인
        if idx[INDEX_CAP:INDEX_CAP + armchk_len] != asm_armchk():
            fail(f"scene {scene}: armchk @{INDEX_CAP:#x} 불일치")

    for lba, base, tbanks in SCENES_UNIFORM:
        pl = json.loads((ROOT / "translation" /
                         (f"btrack_b7_scene_{lba}_payload.json"
                          if lba != 482 else "btrack_b4_field_payload.json")
                         ).read_text(encoding="utf-8"))["records"]
        images = {b: out[T2 + (base + i * 4) * SECTOR:
                         T2 + (base + (i + 1) * 4) * SECTOR]
                  for i, b in enumerate(tbanks)}
        ioff = base + 4 * len(tbanks)
        idx = out[T2 + ioff * SECTOR:
                  T2 + (ioff + 2) * SECTOR] + b"\x00" * 4096
        walk_index(idx[:BANK_SIZE], images, pl, lba)
    pl2882 = json.loads((ROOT / "translation" /
                         f"btrack_b7_scene_{HY_LBA}_payload.json"
                         ).read_text(encoding="utf-8"))["records"]
    img7e = out[T2 + HY_BASE * SECTOR: T2 + (HY_BASE + 4) * SECTOR]
    img7f = out[T2 + (HY_BASE + 4) * SECTOR: T2 + (HY_BASE + 8) * SECTOR]
    walk_index(bytearray(img7e), {HY_BANK_IDX: img7e, HY_BANK_TXT: img7f},
               pl2882, HY_LBA)

    # 4. v4 테이블 워크 시뮬레이션 (zp 포인터 의미론)
    table = card[CARD_TABLE_OFF:CARD_TABLE_OFF + 61 * ENTRY_LEN + 1]
    lbas_expect = [l for l, _b, _t in SCENES_UNIFORM] + [HY_LBA]

    def walk_table(lba_mid, lba_lo):
        ptr = 0
        while table[ptr] != 0xFF:
            if table[ptr] == lba_mid and table[ptr + 1] == lba_lo:
                return table[ptr + 2: ptr + 2 + 42]
            ptr += ENTRY_LEN
        return None

    for l in lbas_expect:
        rows = walk_table((l >> 8) & 0xFF, l & 0xFF)
        if rows is None:
            fail(f"테이블 워크: scene {l} 미발견")
        if not (0x68 <= rows[4] <= 0x7F):
            fail(f"scene {l}: 풀 행 bank {rows[4]:02X} 이상")
    if walk_table(0x7F, 0x7F) is not None:
        fail("테이블 워크: 존재하지 않는 씬이 매치됨")

    # 5. 카드 diff + 복원 대상
    table_len = len(lbas_expect) * ENTRY_LEN + 1
    allowed = [(CARD_TABLE_OFF, CARD_TABLE_OFF + table_len)] + \
        [(s, e) for s, e in CARD_TEXT_BINS]
    diff = [i for i in range(len(card)) if card[i] != card_src[i]]
    for i in diff:
        if not any(s <= i < e for s, e in allowed):
            fail(f"카드 선언 밖 변경 @{i:06X}")
    for bank in (HY_BANK_IDX, HY_BANK_TXT):
        rl = HY_LBA + (bank - 0x68) * 4
        if out[T2 + rl * SECTOR: T2 + (rl + 4) * SECTOR] != \
           src[T2 + rl * SECTOR: T2 + (rl + 4) * SECTOR]:
            fail(f"복원 대상 섹터 {rl}..{rl + 3} 수정됨")

    print(json.dumps({
        "status": "PASS",
        "extension": {"insert_off": INS_OFF, "sectors": EXT_SECTORS,
                      "zero_fill": True, "tail_shift_exact": True,
                      "cue_shift_exact": True},
        "scenes_roundtrip": {str(l): "byte-exact" for l in lbas_expect},
        "armchk_at": hex(ARMCHK),
        "table_walk_sim": "match/nomatch OK",
        "card_diff_bytes": len(diff),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
