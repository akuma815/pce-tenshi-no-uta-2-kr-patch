#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한글판 퀵세이브 → 원본 디스크용 변환 데이터 (2026-10-11 영상 싱크 A/B).
dump_state_all.lua 덤프의 RAM(TurboCD·Super System Card·Main)을 2KB 단위로 한글판 데이터 트랙 섹터와 대조해, 디스크에서 올라온 영역의
한글판↔원본 차이 바이트를 원본 값으로 되돌리는 포크 목록을 쓴다(실행 중 바뀐 바이트 = RAM 값이 한글판 디스크와 다르면 건드리지 않음).
사용: python -X utf8 tools/make_state_to_original.py <덤프 폴더> <한글판 bin> <원본 bin> <출력 pokes.txt>
출력 형식(apply_state_pokes.lua): 한 줄에 「도메인<TAB>주소hex<TAB>바이트hex」.
"""
import sys
from pathlib import Path

dump, kbin, obin, out = sys.argv[1:5]


def iso(binp, extra=0):
    raw = Path(binp).read_bytes()
    start = (0 * 60 + 44) * 75 + 65          # TRACK 02 INDEX 01 00:44:65 (파일 기준, 원본·한글판 동일)
    n = ((2 * 60 + 47) * 75 + 18) - start + extra   # 원본 데이터 트랙 길이 (+ 한글판 확장 섹터)
    return b"".join(raw[(start + i) * 2352 + 16:(start + i) * 2352 + 16 + 2048] for i in range(n)), n


O, on = iso(obin)
K, kn = iso(kbin, 1024)
lines = []
for dom, fn in (("TurboCD RAM", "TurboCD_RAM.bin"), ("Super System Card RAM", "Super_System_Card_RAM.bin"), ("Main Memory", "Main_Memory.bin")):
    ram = Path(dump, fn).read_bytes()
    chunks = len(ram) // 2048
    # 청크마다 32바이트 지문 여러 개를 한글판 데이터 트랙에서 찾아 (RAM 위치 − 디스크 위치) 차이를 투표 → 최다 차이로 청크 전체 일치율 확인(≥ 70%)
    base = [None] * chunks   # 청크 시작에 대응하는 디스크 바이트 오프셋
    for c in range(chunks):
        votes = {}
        for p in range(0, 2048 - 32, 128):
            fp = ram[c * 2048 + p:c * 2048 + p + 32]
            if len(set(fp)) < 8:
                continue
            j = K.find(fp); hits = 0
            while j >= 0 and hits < 4:
                d = j - p; votes[d] = votes.get(d, 0) + 1; hits += 1
                j = K.find(fp, j + 1)
        for d, v in sorted(votes.items(), key=lambda kv: -kv[1])[:3]:
            if d < 0 or d + 2048 > len(K):
                continue
            a = ram[c * 2048:(c + 1) * 2048]; b = K[d:d + 2048]
            if sum(x == y for x, y in zip(a, b)) >= 0.7 * 2048:
                base[c] = d; break
    nmap = npoke = 0
    for c in range(chunks):
        d = base[c]
        if d is None or d + 2048 > on * 2048:
            continue
        nmap += 1
        for i in range(2048):
            k = K[d + i]; o = O[d + i]; r = ram[c * 2048 + i]
            if k != o and r == k:
                lines.append(f"{dom}\t{c * 2048 + i:X}\t{o:02X}"); npoke += 1
    print(f"{dom}: 청크 {chunks} 중 디스크 대응 {nmap}, 되돌릴 바이트 {npoke}")
    print("   ", " ".join(f"{c * 2048:05X}=d{base[c]:X}" for c in range(chunks) if base[c] is not None)[:900])
Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
print("pokes", len(lines))
