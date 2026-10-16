#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""b46 카드 코드 실행 검증 (미니 HuC6280 에뮬레이터, 2026-10-11).

  ① SERVE46: 레코드 시작(FLAG=2, TBANK/CUR, BITCNT=0, PEND=0)에서 serve 를 반복 호출 → C=1(끝)까지 나온 바이트 = 원문(압축 전).
  ② ARMCHK46: 씬마다 모든 키에 대해 엔진 상태($4B/$4C, $22D0)를 꾸며 호출 → 일치 + TBANK/CUR = 레코드 위치 + $4B/$4C += 원문길이-1.
     키가 아닌 오프셋(키-1)은 거부(C=1).
  ③ 조사 게이트: 배정 한글·1바이트 한글 전부 LASTHI/LASTLO → JOSA_B 직전 A = 종류*2 + 받침.
사용: python -X utf8 tools/verify_b46_emu.py [레코드 표본 수(기본 전부)]
"""
from __future__ import annotations
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
argv = sys.argv[1:]; sys.argv = ["x"]
import huc_mini_emu as E
import build_btrack_b46_hook_build as m
import build_btrack_b9_hook_build as b9
import build_btrack_b28_hook_build as b28
from build_btrack_b7_hook_build import FLAG, TBANK, CURL, CURH, SCRATCH, CARD_TABLE_OFF, ENTRY_LEN

card = m.OUT_CARD.read_bytes()
assert len(card) == 0x40000


def cpu_new():
    c = E.CPU(card)
    c.mpr = [0xFF, 0xF8, 0x81, m.DEC_BANK, 0x82, 0x83, 0x84, 0x00]
    c.ram.setdefault(0x84, bytearray(0x2000))
    return c


def wr(c, a, v): c.wr(a, v)
def rd(c, a): return c.rd(a)


def serve_record(bank, addr, limit=20000):
    c = cpu_new()
    wr(c, FLAG, 2); wr(c, TBANK, bank); wr(c, CURL, addr & 0xFF); wr(c, CURH, addr >> 8)
    wr(c, m.BITCNT, 0); wr(c, m.PEND, 0)
    out = bytearray()
    for _ in range(limit):
        mpr0 = list(c.mpr)
        c.call(m.SERVE46, max_steps=10 ** 7)
        assert c.mpr == mpr0, "MPR 복원 실패"
        if c.c:
            return bytes(out), c
        out.append(rd(c, 0x2D80))
    raise AssertionError("끝나지 않음")


def main():
    rows = m.records()
    # 레코드 위치: 카드 인덱스에서 (모델 검증과 같은 해석)
    want = {(lba, k): (bytes.fromhex(h), n) for lba, k, h, n in rows}
    entries = {}
    for i, lba in enumerate(b9.SCENES_B9):
        t = CARD_TABLE_OFF + i * ENTRY_LEN + 2
        hb, base = card[t + 4], card[t + 5] << 8 | card[t + 6]
        R = lambda b, a: card[b * 0x2000 + a - 0xA000]
        for kb in range(24):
            bank = R(hb, base + 2 + kb * 3); p = R(hb, base + 3 + kb * 3) | R(hb, base + 4 + kb * 3) << 8
            cur = 0
            while True:
                d = R(bank, p)
                if d == 0xFE: break
                if d == 0xFF: cur = R(bank, p + 1) << 8 | R(bank, p + 2); p += 3
                else: cur += d; p += 1
                tb, ta = R(bank, p), R(bank, p + 1) | R(bank, p + 2) << 8
                l1 = R(bank, p + 3)
                if l1 == 0xFF: l1 = R(bank, p + 4) | R(bank, p + 5) << 8; p += 6
                else: p += 4
                entries[(lba, kb << 13 | cur)] = (tb, ta, l1)
    # ① serve
    uniq = {}
    for key, (tb, ta, l1) in entries.items():
        uniq.setdefault((tb, ta), want[key][0])
    keys = sorted(uniq)
    n = int(argv[0]) if argv else len(keys)
    random.seed(46); sample = keys if n >= len(keys) else random.sample(keys, n)
    for j, (tb, ta) in enumerate(sample):
        got, c = serve_record(tb, ta)
        assert got + b"\x00" == uniq[(tb, ta)], f"serve 불일치 {tb:02X}:{ta:04X}\n got {got.hex()}\n exp {uniq[(tb, ta)].hex()}"
        assert rd(c, FLAG) == 0
    print(f"① serve OK: 레코드 {len(sample)}/{len(keys)}")
    # ② armchk (기본 경로: $53=0, $2E69=0, $4C 를 $A000 창으로, $22D0 로 kb 맞춤)
    ok = rej = 0
    for (lba, key), (tb, ta, l1) in sorted(entries.items()):
        i = b9.SCENES_B9.index(lba)
        t = CARD_TABLE_OFF + i * ENTRY_LEN + 2
        for probe_key, expect in ((key, True), (key - 1, (lba, key - 1) in entries)):
            if probe_key < 0: continue
            kb, off = probe_key >> 13, probe_key & 0x1FFF
            c = cpu_new()
            c.mpr[5] = card[t + 4]                           # 리더가 MPR5 = IBANK 로 매핑
            for j in range(42): wr(c, SCRATCH + j, card[t + j])
            wr(c, 0x2053, 0); wr(c, 0x2E69, 0)
            hi = 0xA0 | (off >> 8)                           # $4C: $A000 창 → (>>5)=5
            wr(c, 0x204C, hi); wr(c, 0x204B, off & 0xFF)
            wr(c, 0x22D0, (kb + 0x68 - (5 + 8)) & 0xFF)
            wr(c, FLAG, 0)
            c.call(m.ARMCHK46, max_steps=10 ** 6)
            if expect:
                tb2, ta2, l12 = entries[(lba, probe_key)]
                assert c.c == 0, f"armchk 미일치 scene {lba} key {probe_key:05X}"
                assert (rd(c, TBANK), rd(c, CURL) | rd(c, CURH) << 8) == (tb2, ta2)
                newp = (hi << 8 | (off & 0xFF)) + l12
                assert (rd(c, 0x204C) << 8 | rd(c, 0x204B)) == newp & 0xFFFF
                assert rd(c, FLAG) == 2 and rd(c, m.PEND) == 0 and rd(c, m.BITCNT) == 0
                ok += 1
            else:
                assert c.c == 1, f"armchk 오일치 scene {lba} key {probe_key:05X}"
                rej += 1
    print(f"② armchk OK: 일치 {ok}, 거부 {rej}")
    # ③ 조사 게이트
    asg = json.loads(b28.ASSIGN.read_text(encoding="utf-8"))["assignment"]
    omap = json.loads(b28.ONEBYTE.read_text(encoding="utf-8"))["map"]
    def batchim(ch): return 1 if (ord(ch) - 0xAC00) % 28 else 0
    cases = [(int(e["sjis"][:2], 16), int(e["sjis"][2:], 16), batchim(ch)) for ch, e in asg.items()]
    cases += [(b28.ONEBYTE_ROW_HI, int(k, 16), batchim(v["ch"])) for k, v in omap.items()]
    gerr = 0
    for kind in range(4):
        for lh, ll, bt in cases:
            c = cpu_new()
            c.mpr[5] = m.DEC_BANK; c.mpr[3] = 0x1F
            wr(c, b28.LASTHI, lh); wr(c, b28.LASTLO, ll)
            c.s = 0xF0
            wr(c, 0x2100 + 0xF0 - 1 + 0x0A, b28.PRINTER_RET & 0xFF); wr(c, 0x2100 + 0xF0 - 1 + 0x0B, b28.PRINTER_RET >> 8)
            c.x = kind * 2; c.pc = m.GATE46
            for _ in range(500):
                if c.pc in (b28.JOSA_B, b28.JOSA_GNO): break
                c.step()
            if c.pc != b28.JOSA_B or c.a != kind * 2 + bt:
                gerr += 1
    print(f"③ 조사 게이트: {4 * len(cases)}건 중 오류 {gerr}")
    assert gerr == 0


if __name__ == "__main__":
    main()
