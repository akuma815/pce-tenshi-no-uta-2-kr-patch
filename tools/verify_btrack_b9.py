#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B9 산출물 검증.

  1. 트랙 확장 구조 + cue 시프트
  2. **전 디스크 diff**: 허용 = 엔진 패치 4개 + 삽입 구간뿐 (풀 섹터 부재 확인)
  3. 카드 768KB, diff = 선언 범위(테이블+텍스트 풀+인덱스+armchk)뿐
  4. **serve 시뮬레이션을 카드 씬 테이블에서 출발**: 테이블 엔트리 →
     IBANK/IBASE → 인덱스 매직/버킷 워크(base 반영) → 카드 텍스트 read —
     54씬 전 레코드 바이트 왕복 + 길이 필드 + 씬당 전수 커버
  5. armchk_v3 사본이 모든 인덱스 뱅크 오프셋 $0880 에 동일 바이트로 존재,
     어떤 인덱스도 armchk 구간과 겹치지 않음
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b9_hook_build import (
    OUT_BIN, OUT_CUE, CARD_OUT, CARD_SIZE, SCENES_B9, EXT_BANKS,
    ARMCHK_OFF, ARMCHK_CARD_OFF, asm_armchk_v3, asm_reader_v3m, payload,
)
from build_btrack_b8_hook_build import (
    EXT_SECTORS, INS_OFF, asm_loader_v4,
)
from build_btrack_b7_hook_build import (
    make_slice, asm_bank81, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP,
    WINDOW_LO, LOADER, FLAG, INDEX_MAGIC, ENTRY_LEN, ROWS_IMG_LEN, BANK_SIZE,
    CARD_TABLE_OFF, SRC_BIN, SRC_CUE, CARD_SRC,
)

SECTOR = 2048

# b10 래퍼가 주입: 디스크 diff 에서 추가로 허용할 (파일오프셋 s, e) 목록.
# 이 구간의 '내용' 검증은 주입한 쪽(verify_btrack_b10)이 책임진다.
EXTRA_ALLOWED: list[tuple[int, int]] = []


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
    if len(card) != CARD_SIZE:
        fail(f"카드 크기 {len(card)} != {CARD_SIZE}")

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

    # 2. 전 디스크 diff = 엔진 패치 4개뿐
    loader = asm_loader_v4().resolve()
    wnd_slice_addr = LOADER + len(loader)
    slice_src = bytes(src[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader_v3m(wnd_reader_addr).resolve()
    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)
    patches = [(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8))),
               (eng_off(SLICE_LO), bank81),
               (eng_off(WINDOW_LO), loader + wslice + reader),
               (eng_off(FLAG), bytes(6))]
    for off, data in patches:
        if out[off:off + len(data)] != data:
            fail(f"엔진 패치 불일치 @{off:07X}")
    allowed = sorted([(off, off + len(d)) for off, d in patches]
                     + list(EXTRA_ALLOWED))
    pos = 0
    for s_, e_ in allowed:
        if out[pos:s_] != src[pos:s_]:
            fail(f"선언 밖 디스크 변경 ({pos:07X}..{s_:07X})")
        pos = e_
    if out[pos:INS_OFF] != src[pos:INS_OFF]:
        fail(f"선언 밖 디스크 변경 ({pos:07X}..{INS_OFF:07X})")

    # 3+5. 카드 diff + armchk
    armchk = asm_armchk_v3()
    src_ext = CARD_SRC.read_bytes() + b"\xFF" * (CARD_SIZE - 256 * 1024)

    # 4. serve 시뮬레이션 — 카드 테이블에서 출발
    t_off = CARD_TABLE_OFF
    seen_lbas = []
    idx_banks: set[int] = set()
    text_banks_hit: set[int] = set()
    idx_extents: list[tuple[int, int, int]] = []  # (bank, off, end) 겹침 검사
    total_entries = 0
    pos = t_off
    while card[pos] != 0xFF or card[pos + 1:pos + 2] == b"":
        lba = (card[pos] << 8) | card[pos + 1]
        rows = card[pos + 2:pos + 2 + ROWS_IMG_LEN * 2]
        if rows[0] != 0xFF:
            fail(f"scene {lba}: 행0 시작 != FF (RUN 무동작 규약)")
        ibank, ibase_hi = rows[4], rows[5]
        for i, v in enumerate(rows):
            if i not in (4, 5) and v != 0xFF:
                fail(f"scene {lba}: 행 이미지 byte{i} = {v:02X} != FF")
        if not (0xA0 <= ibase_hi <= 0xBF):
            fail(f"scene {lba}: IBASE {ibase_hi:02X} 창 밖")
        idx_banks.add(ibank)
        ioff = (ibase_hi << 8) - 0xA000
        idx0 = ibank * BANK_SIZE + ioff
        if card[idx0:idx0 + 2] != INDEX_MAGIC:
            fail(f"scene {lba}: 인덱스 매직 불일치 @{idx0:06X}")
        pl = payload(lba)
        by_key = {int.from_bytes(bytes.fromhex(r["source_key_u24le"]),
                                 "little"): r for r in pl}
        seen = set()
        max_end = idx0 + 2
        for kb in range(24):
            p = card[idx0 + 2 + kb * 2] | (card[idx0 + 3 + kb * 2] << 8)
            cur = ibank * BANK_SIZE + (p - 0xA000)
            while card[cur] != 0xFF:
                oh, ol, bank, alo, ahi, llo, lhi = card[cur:cur + 7]
                key = (kb << 13) | (oh << 8) | ol
                r = by_key.get(key)
                if r is None:
                    fail(f"scene {lba}: 키 {key:06X} 무대응")
                if r["id"] in seen:
                    fail(f"scene {lba}: {r['id']} 중복")
                seen.add(r["id"])
                addr = alo | (ahi << 8)
                tpos = bank * BANK_SIZE + (addr - 0xA000)
                end = card.index(0, tpos)
                if card[tpos:end + 1] != bytes.fromhex(r["encoded_hex"]):
                    fail(f"scene {lba}: {r['id']} serve 불일치 (bank {bank:02X})")
                if (llo | (lhi << 8)) != r["original_raw_length"] - 1:
                    fail(f"scene {lba}: {r['id']} 길이 불일치")
                text_banks_hit.add(bank)
                cur += 7
                total_entries += 1
            max_end = max(max_end, cur + 1)
        if len(seen) != len(pl):
            fail(f"scene {lba}: 커버 {len(seen)} != {len(pl)}")
        idx_extents.append((ibank, ioff, max_end - ibank * BANK_SIZE))
        seen_lbas.append(lba)
        pos += ENTRY_LEN
    if seen_lbas != SCENES_B9:
        fail(f"테이블 씬 목록 불일치: {len(seen_lbas)}개")
    if card[pos] != 0xFF:
        fail("테이블 종결 FF 없음")

    # 5. armchk = $1F 단일 사본, 인덱스 뱅크 0x880 홀은 FF 예약 유지
    if card[ARMCHK_CARD_OFF:ARMCHK_CARD_OFF + len(armchk)] != armchk:
        fail("armchk_v3 @1F 불일치")
    for bnk in sorted(idx_banks):
        lo = bnk * BANK_SIZE + ARMCHK_OFF
        if set(card[lo:lo + len(armchk)]) != {0xFF}:
            fail(f"인덱스 뱅크 {bnk:02X} 홀 비-FF")
    for bnk, ioff, iend in idx_extents:
        if max(ioff, ARMCHK_OFF) < min(iend, ARMCHK_OFF + len(armchk)):
            fail(f"인덱스가 예약 홀과 겹침 bank {bnk:02X} @{ioff:04X}")
    ext = set(EXT_BANKS)
    if not (text_banks_hit <= ext and idx_banks <= ext):
        fail("확장 뱅크 목록 밖 사용 (Arcade Card 섀도우 $40-$43 포함 금지)")
    if text_banks_hit & idx_banks:
        fail(f"텍스트/인덱스 뱅크 겹침: {sorted(text_banks_hit & idx_banks)}")

    # 3. 카드 diff 전수 (선언 = 테이블 + armchk@1F + 텍스트/인덱스 뱅크)
    tbl_end = t_off + len(SCENES_B9) * ENTRY_LEN + 1
    allowed_c = [(t_off, tbl_end),
                 (ARMCHK_CARD_OFF, ARMCHK_CARD_OFF + len(armchk))]
    for bnk in sorted(text_banks_hit):
        allowed_c.append((bnk * BANK_SIZE, (bnk + 1) * BANK_SIZE))
    for bnk in sorted(idx_banks):
        allowed_c.append((bnk * BANK_SIZE, (bnk + 1) * BANK_SIZE))
    diff = 0
    for i in range(len(card)):
        if card[i] != src_ext[i]:
            diff += 1
            if not any(s <= i < e for s, e in allowed_c):
                fail(f"카드 선언 밖 변경 @{i:06X}")

    print(json.dumps({
        "status": "PASS",
        "scenes": len(seen_lbas),
        "entries_total": total_entries,
        "text_banks": sorted(f"{b:02X}" for b in text_banks_hit),
        "index_banks": sorted(f"{b:02X}" for b in idx_banks),
        "armchk_bytes": len(armchk),
        "disc_diff": "engine patches + extension only",
        "card_diff_bytes": diff,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
