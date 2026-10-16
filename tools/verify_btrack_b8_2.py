#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B8.2 최종 산출물 검증 (4씬 serve 시뮬레이션 + 구조).

  1. 트랙 확장 구조 + cue 시프트 (b8 검증과 동일 기준)
  2. 4씬(482/290/2882/578) 인덱스 전수 워크 + serve 시뮬레이션 —
     dedupe(다대일)·카드 상주·00-run bin 포함 바이트 왕복
  3. 씬 테이블 4엔트리: 행0 = 인덱스 행, bank 가 씬별 기대값(리더 v2 전제)
  4. 카드 diff = 선언 범위(테이블+2882 bin+578 bin)뿐
  5. 복원 행 대상 섹터(각 씬 자신의 extent 내 섹터) 무수정
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b8_2_hook_build import (
    OUT_BIN, OUT_CUE, CARD_OUT, SCENES_UNIFORM,
    S578_LBA, S578_BASE, S578_BANK_IDX,
)
from build_btrack_b8_hook_build import (
    ARMCHK, INDEX_CAP, EXT_SECTORS, INS_OFF, asm_armchk,
)
from build_btrack_b7_6_hook_build import (
    HY_LBA, HY_BASE, HY_BANK_IDX, HY_BANK_TXT, CARD_TEXT_BINS,
)
from build_btrack_b7_hook_build import (
    T2, INDEX_MAGIC, ENTRY_LEN, CARD_TABLE_OFF, SRC_BIN, SRC_CUE, CARD_SRC,
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
    armchk = asm_armchk()

    # 1. 확장 구조 + cue
    ins_len = EXT_SECTORS * SECTOR
    if len(out) != len(src) + ins_len:
        fail("bin 크기 불일치")
    if any(out[INS_OFF:INS_OFF + ins_len]):
        fail("확장 영역 비-00")
    if out[INS_OFF + ins_len:] != src[INS_OFF:]:
        fail("꼬리 시프트 불일치")
    a = parse_cue_indexes(SRC_CUE.read_text(encoding="ascii"))
    b = parse_cue_indexes(OUT_CUE.read_text(encoding="ascii"))
    for t in a:
        if b.get(t) != a[t] + (EXT_SECTORS if t >= 3 else 0):
            fail(f"cue 트랙 {t} 시프트 불일치")

    # 2. serve 시뮬레이션
    def read_text(images, bank, addr):
        off = addr - 0xA000
        if not (0 <= off < BANK_SIZE):
            fail(f"addr {addr:04X} 창 밖")
        blob = images[bank] if bank in images else \
            card[bank * BANK_SIZE:(bank + 1) * BANK_SIZE]
        end = blob.index(0, off)
        return bytes(blob[off:end + 1])

    def walk_index(idx, images, payload, scene):
        by_key = {int.from_bytes(bytes.fromhex(r["source_key_u24le"]),
                                 "little"): r for r in payload}
        if idx[0:2] != INDEX_MAGIC:
            fail(f"scene {scene}: 매직 불일치")
        if bytes(idx[INDEX_CAP:INDEX_CAP + len(armchk)]) != armchk:
            fail(f"scene {scene}: armchk 불일치")
        seen = set()
        for kb in range(24):
            p = idx[2 + kb * 2] | (idx[3 + kb * 2] << 8)
            cur = p - 0xA000
            while idx[cur] != 0xFF:
                oh, ol, bank, alo, ahi, llo, lhi = idx[cur:cur + 7]
                key = (kb << 13) | (oh << 8) | ol
                r = by_key.get(key)
                if r is None:
                    fail(f"scene {scene}: 키 {key:06X} 무대응")
                if r["id"] in seen:
                    fail(f"scene {scene}: {r['id']} 중복")
                seen.add(r["id"])
                if read_text(images, bank, alo | (ahi << 8)) != \
                        bytes.fromhex(r["encoded_hex"]):
                    fail(f"scene {scene}: {r['id']} serve 불일치 (bank {bank:02X})")
                if (llo | (lhi << 8)) != r["original_raw_length"] - 1:
                    fail(f"scene {scene}: {r['id']} 길이 불일치")
                cur += 7
        if len(seen) != len(payload):
            fail(f"scene {scene}: {len(seen)} != {len(payload)}")

    def payload(lba):
        name = ("btrack_b4_field_payload.json" if lba == 482
                else f"btrack_b7_scene_{lba}_payload.json")
        return json.loads((ROOT / "translation" / name
                           ).read_text(encoding="utf-8"))["records"]

    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        images = {b: out[T2 + (base + i * 4) * SECTOR:
                         T2 + (base + (i + 1) * 4) * SECTOR]
                  for i, b in enumerate(tbanks)}
        ioff = base + 4 * len(tbanks)
        images[ibank] = out[T2 + ioff * SECTOR: T2 + (ioff + 2) * SECTOR] \
            + b"\x00" * 4096
        walk_index(images[ibank], images, payload(lba), lba)
    images = {HY_BANK_IDX: out[T2 + HY_BASE * SECTOR:
                               T2 + (HY_BASE + 4) * SECTOR],
              HY_BANK_TXT: out[T2 + (HY_BASE + 4) * SECTOR:
                               T2 + (HY_BASE + 8) * SECTOR]}
    walk_index(images[HY_BANK_IDX], images, payload(HY_LBA), HY_LBA)
    img76 = out[T2 + S578_BASE * SECTOR: T2 + (S578_BASE + 4) * SECTOR]
    walk_index(img76, {S578_BANK_IDX: img76}, payload(S578_LBA), S578_LBA)

    # 3. 씬 테이블: 4엔트리, 행0 = 인덱스 행 (리더 v2 전제)
    expect = [(l, ib) for l, _b, _t, ib in SCENES_UNIFORM] + \
        [(HY_LBA, HY_BANK_IDX), (S578_LBA, S578_BANK_IDX)]
    t = card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(expect) * ENTRY_LEN + 1]
    pos = 0
    for lba, ibank in expect:
        got = (t[pos] << 8) | t[pos + 1]
        if got != lba:
            fail(f"테이블 lba {got} != {lba}")
        if t[pos + 2 + 4] != ibank:
            fail(f"scene {lba}: 행0 bank {t[pos + 2 + 4]:02X} != 인덱스 {ibank:02X}")
        pos += ENTRY_LEN
    if t[pos] != 0xFF:
        fail("테이블 종결 FF 없음")

    # 4. 카드 diff
    allowed = [(CARD_TABLE_OFF, CARD_TABLE_OFF + len(expect) * ENTRY_LEN + 1)] \
        + [(s, e) for s, e in CARD_TEXT_BINS] + [(0x02D59E, 0x02E000)]
    diff = [i for i in range(len(card)) if card[i] != card_src[i]]
    for i in diff:
        if not any(s <= i < e for s, e in allowed):
            fail(f"카드 선언 밖 변경 @{i:06X}")

    # 5. 복원 대상 섹터 무수정
    restore_targets = []
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        restore_targets += [(lba + (b - 0x68) * 4, 4) for b in tbanks]
        restore_targets += [(lba + (ibank - 0x68) * 4, 2)]
    restore_targets += [(HY_LBA + (HY_BANK_IDX - 0x68) * 4, 4),
                        (HY_LBA + (HY_BANK_TXT - 0x68) * 4, 4),
                        (S578_LBA + (S578_BANK_IDX - 0x68) * 4, 4)]
    for rl, n in restore_targets:
        if out[T2 + rl * SECTOR: T2 + (rl + n) * SECTOR] != \
           src[T2 + rl * SECTOR: T2 + (rl + n) * SECTOR]:
            fail(f"복원 대상 섹터 {rl}..{rl + n - 1} 수정됨")

    print(json.dumps({
        "status": "PASS",
        "scenes_roundtrip": {str(l): "byte-exact"
                             for l, _ in expect},
        "table_index_first": True,
        "card_diff_bytes": len(diff),
        "extension_ok": True,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
