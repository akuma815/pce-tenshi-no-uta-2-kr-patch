#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B7.6 하이브리드 최종 산출물 검증 (armchk/serve 시뮬레이션).

검증 항목 (fail-closed):
  1. 균일 씬(482/290) 풀 섹터가 b7.5 빌드와 바이트 동일 (회귀 0)
  2. 엔진 패치 영역(벡터/뱅크81/창)이 b7.5 와 바이트 동일
  3. 2882 인덱스: 24버킷 전수 워크 — 각 엔트리를 armchk 산식으로 해석하고
     serve 시뮬레이션(NUL 까지 read)으로 텍스트를 복원, 페이로드와 바이트
     비교. 카드 상주 레코드는 카드 파일에서 읽는다.
  4. 레코드↔엔트리 전단사 (누락/중복 0)
  5. 모든 레코드가 MPR5 창($A000-$BFFF) 안에 완결 (뱅크 경계 침범 0)
  6. 카드 diff = 씬 테이블 + 선언 텍스트 bin 내부뿐, 전부 CDL-cold FF-run
  7. 2882 복원 행이 가리키는 원본 섹터(2970..2977)는 무수정
  8. 씬 테이블 디코드: 3엔트리 lba/행 구성 확인
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_6_hook_build import (
    UNIFORM_SCENES, HY_LBA, HY_BASE, HY_SECTORS, HY_BANK_IDX, HY_BANK_TXT,
    CARD_TEXT_BINS, FONT_TAIL, OUT_BIN, CARD_OUT,
)
from build_btrack_b7_hook_build import (
    T2, eng_off, VECTOR, SLICE_LO, SLICE_HI, WINDOW_LO, WINDOW_HI,
    INDEX_MAGIC, INDEX_CAP, ENTRY_LEN, ROWS_IMG_LEN,
    CARD_TABLE_OFF, SRC_BIN, CARD_SRC,
)

B75_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b7.bin"
SECTOR = 2048
BANK_SIZE = 8192


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    out = OUT_BIN.read_bytes()
    b75 = B75_BIN.read_bytes()
    src = SRC_BIN.read_bytes()
    card = CARD_OUT.read_bytes()
    card_src = CARD_SRC.read_bytes()

    # 1. 균일 씬 풀 = b7.5 동일
    for lba, base, _t in UNIFORM_SCENES:
        a = out[T2 + base * SECTOR: T2 + (base + 14) * SECTOR]
        b = b75[T2 + base * SECTOR: T2 + (base + 14) * SECTOR]
        if a != b:
            fail(f"scene {lba} 풀이 b7.5 와 다름")
    # 2. 엔진 패치 = b7.5 동일
    for lo, hi, name in ((eng_off(VECTOR), eng_off(VECTOR) + 3, "vector"),
                         (eng_off(SLICE_LO), eng_off(SLICE_HI), "bank81"),
                         (eng_off(WINDOW_LO), eng_off(WINDOW_HI), "window")):
        if out[lo:hi] != b75[lo:hi]:
            fail(f"엔진 패치 {name} 이 b7.5 와 다름")

    # 3~5. 2882 인덱스 전수 워크 + serve 시뮬레이션
    pl = json.loads((ROOT / "translation" /
                     f"btrack_b7_scene_{HY_LBA}_payload.json"
                     ).read_text(encoding="utf-8"))["records"]
    by_key = {}
    for r in pl:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        by_key[key] = r
    img = {HY_BANK_IDX: out[T2 + HY_BASE * SECTOR: T2 + (HY_BASE + 4) * SECTOR],
           HY_BANK_TXT: out[T2 + (HY_BASE + 4) * SECTOR:
                            T2 + (HY_BASE + 8) * SECTOR]}
    idx = img[HY_BANK_IDX]
    if idx[0:2] != INDEX_MAGIC:
        fail("2882 인덱스 매직 불일치")

    def read_text(bank, addr):
        """serve 시뮬: (bank, $A000상대) 에서 NUL 포함까지 read."""
        off = addr - 0xA000
        if not (0 <= off < BANK_SIZE):
            fail(f"addr {addr:04X} 가 MPR5 창 밖")
        blob = img[bank] if bank in img else \
            card[bank * BANK_SIZE:(bank + 1) * BANK_SIZE]
        end = blob.index(0, off)
        if end >= BANK_SIZE:
            fail("레코드가 뱅크 창을 넘음")
        return bytes(blob[off:end + 1]), bank in img

    seen = set()
    ram_cnt = card_cnt = 0
    for kb in range(24):
        p = idx[2 + kb * 2] | (idx[3 + kb * 2] << 8)
        cur = p - 0xA000
        while idx[cur] != 0xFF:
            oh, ol, bank, alo, ahi, llo, lhi = idx[cur:cur + 7]
            key = (kb << 13) | (oh << 8) | ol
            r = by_key.get(key)
            if r is None:
                fail(f"인덱스 키 {key:06X} 에 대응 레코드 없음")
            if r["id"] in seen:
                fail(f"{r['id']}: 중복 엔트리")
            seen.add(r["id"])
            text, is_ram = read_text(bank, alo | (ahi << 8))
            if text != bytes.fromhex(r["encoded_hex"]):
                fail(f"{r['id']}: serve 재현 불일치 (bank {bank:02X})")
            if (llo | (lhi << 8)) != r["original_raw_length"] - 1:
                fail(f"{r['id']}: 원문 길이 필드 불일치")
            if is_ram:
                ram_cnt += 1
            else:
                card_cnt += 1
            cur += 7
    if len(seen) != len(pl):
        fail(f"엔트리 {len(seen)} != 레코드 {len(pl)}")

    # 6. 카드 diff 전수: 씬 테이블 ∪ 텍스트 bin 안에서만, bin 은 원본 FF
    table_len = 3 * ENTRY_LEN + 1                # 3씬 × 44B + 종결 FF
    allowed = [(CARD_TABLE_OFF, CARD_TABLE_OFF + table_len)] + \
        [(s, e) for s, e in CARD_TEXT_BINS]
    diff = [i for i in range(len(card)) if card[i] != card_src[i]]
    for i in diff:
        if not any(s <= i < e for s, e in allowed):
            fail(f"카드 선언 밖 변경 @{i:06X}")
    for s, e in CARD_TEXT_BINS:
        if set(card_src[s:e]) != {0xFF}:
            fail(f"카드 bin {s:06X}: 원본이 FF-run 아님")
        fs, fe = FONT_TAIL
        if max(s, fs) < min(e, fe):
            fail(f"카드 bin {s:06X}: 폰트 꼬리 침범")

    # 7. 2882 복원 행 대상 섹터 무수정
    for bank in (HY_BANK_IDX, HY_BANK_TXT):
        rl = HY_LBA + (bank - 0x68) * 4
        if out[T2 + rl * SECTOR: T2 + (rl + 4) * SECTOR] != \
           src[T2 + rl * SECTOR: T2 + (rl + 4) * SECTOR]:
            fail(f"복원 대상 섹터 {rl}..{rl + 3} 이 수정됨")

    # 8. 씬 테이블 디코드
    t = card[CARD_TABLE_OFF:CARD_TABLE_OFF + table_len]
    pos = 0
    lbas = []
    for _ in range(3):
        lba = (t[pos] << 8) | t[pos + 1]
        lbas.append(lba)
        rows = t[pos + 2: pos + 2 + ROWS_IMG_LEN * 2]
        # 풀 세트 첫 행의 bank 가 유효 범위인지
        if not (0x68 <= rows[4] <= 0x7F):
            fail(f"scene {lba}: 풀 행 bank {rows[4]:02X} 이상")
        pos += ENTRY_LEN
    if t[pos] != 0xFF:
        fail("씬 테이블 종결 FF 없음")
    if lbas != [l for l, _b, _t2 in UNIFORM_SCENES] + [HY_LBA]:
        fail(f"씬 테이블 lba 불일치: {lbas}")

    print(json.dumps({
        "status": "PASS",
        "uniform_scenes_identical_to_b7_5": True,
        "engine_patch_identical_to_b7_5": True,
        "scene_2882": {"records": len(pl), "ram": ram_cnt, "card": card_cnt,
                       "roundtrip": "byte-exact"},
        "card_diff_bytes": len(diff),
        "restore_targets_untouched": True,
        "scene_table": lbas,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
