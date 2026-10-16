#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빌드 간 퀵세이브 변환 데이터 생성 (2026-10-11).
dump_state_ram.lua 의 덤프(sscram.bin·cdram.bin)로 상주 씬을 찾고(디스크 대조), 옛 빌드 → 새 빌드 디스크 차이(그 씬 범위) + 새 카드의 씬 테이블 행을
convert_state_b53.lua 용 PROBE_CONV 파일로 쓴다.
사용: python -X utf8 tools/make_state_conversion.py <덤프폴더> <옛 bin> <새 bin> <새 카드> <출력 conv 파일>
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
dump, old_bin, new_bin, new_card, out = sys.argv[1:6]
sys.argv = ["x"]
from build_btrack_b7_hook_build import T2, CARD_TABLE_OFF, ENTRY_LEN
import build_btrack_b9_hook_build as b9

ram = Path(dump, "sscram.bin").read_bytes()
cd = Path(dump, "cdram.bin").read_bytes()
a = Path(old_bin).read_bytes()[T2:]
b = Path(new_bin).read_bytes()[T2:]
best = max(((sum(x == y for x, y in zip(a[l * 2048:l * 2048 + 0x10000], ram[:0x10000])) / 0x10000, l) for l in b9.SCENES_B9))
score, lba = best
assert score > 0.95, f"상주 씬 불명확 {best}"
lo = lba * 2048
diffs = [i for i in range(lo, lo + len(ram)) if a[i] != b[i]]
card = Path(new_card).read_bytes()
k = b9.SCENES_B9.index(lba)
t = CARD_TABLE_OFF + k * ENTRY_LEN + 2
flag = cd[0x88F9]
Path(out).write_text(";".join(f"{i - lo:X}:{a[i - 8:i + 9].hex()}:{b[i]:02X}" for i in diffs) + "\n" + card[t:t + 42].hex() + "\n")
print(f"scene {lba} (match {score:.3f}) disc diffs {len(diffs)} row old {cd[0x88CC:0x88CF].hex()} -> new {card[t + 4:t + 7].hex()} FLAG={flag:02X}")
if flag != 0:
    print("경고: 대사 서브 중(FLAG≠0) 저장 — 변환 후 대사 한 줄이 깨질 수 있음")
