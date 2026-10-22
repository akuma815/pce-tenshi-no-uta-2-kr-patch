#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RetroArch(Beetle PCE Fast) 한글판 세이브 스테이트 → 원본 디스크용 스테이트 (2026-10-22, 제보 A/B 대조용).

make_state_to_original.py 와 같은 원리: 스테이트 안의 RAM(BaseRAM·CDRAM·SysCardRAM)을 2KB 청크마다 한글판 데이터
트랙과 지문 대조해 디스크 유래 위치를 찾고, 「RAM 값 == 한글판 디스크 값 ≠ 원본 디스크 값」인 바이트만 원본 값으로
되돌린다(실행 중 바뀐 바이트는 유지). 카드 ROM 은 스테이트에 없으므로 원본 BIOS 로 부팅한 RetroArch 에서 그대로 읽힌다.
사용: python -X utf8 tools/convert_ra_state_to_original.py <stateN(RZIP 또는 raw)> <한글판 bin> <원본 bin> <출력 state>
출력은 비압축 RASTATE 로 쓴다(RetroArch 가 그대로 읽는다).
"""
import struct
import sys
import zlib
from pathlib import Path

T2 = 7_914_480
DATA_SECTORS = 9328


def unrzip(b: bytes) -> bytes:
    if b[:6] != b"#RZIPv":
        return b
    pos, out = 20, bytearray()
    while pos < len(b):
        n = struct.unpack_from("<I", b, pos)[0]
        pos += 4
        out += zlib.decompress(b[pos:pos + n])
        pos += n
    return bytes(out)


def data_track(binp: str) -> bytes:
    raw = Path(binp).read_bytes()
    return raw[T2:T2 + DATA_SECTORS * 2048]


def find_sections(mem: bytes):
    """Mednafen 스테이트(MDFNSVST) 안의 (섹션, 필드, 오프셋, 길이) 목록."""
    out = []
    p = 32
    while p < len(mem):
        name = mem[p:p + 32].rstrip(b"\0").decode("ascii", "replace")
        sz = struct.unpack_from("<I", mem, p + 32)[0]
        p += 36
        q, end = p, p + sz
        while q < end:
            nl = mem[q]
            nm = mem[q + 1:q + 1 + nl].decode("ascii", "replace")
            q += 1 + nl
            vs = struct.unpack_from("<I", mem, q)[0]
            q += 4
            out.append((name, nm, q, vs))
            q += vs
        p = end
    return out


def revert(ram: bytes, K: bytes, O: bytes, label: str, rng=None):
    ram = bytearray(ram)
    chunks = len(ram) // 2048
    base = [None] * chunks
    for c in range(chunks):
        votes = {}
        for p in range(0, 2048 - 32, 128):
            fp = bytes(ram[c * 2048 + p:c * 2048 + p + 32])
            if len(set(fp)) < 8:
                continue
            j = K.find(fp)
            hits = 0
            while j >= 0 and hits < 4:
                d = j - p
                votes[d] = votes.get(d, 0) + 1
                hits += 1
                j = K.find(fp, j + 1)
        for d, v in sorted(votes.items(), key=lambda kv: -kv[1])[:3]:
            if d < 0 or d + 2048 > len(K):
                continue
            a = ram[c * 2048:(c + 1) * 2048]
            b = K[d:d + 2048]
            if sum(x == y for x, y in zip(a, b)) >= 0.7 * 2048:
                base[c] = d
                break
    nmap = npoke = 0
    for c in range(chunks):
        d = base[c]
        if d is None:
            continue
        nmap += 1
        for i in range(2048):
            if rng and not any(lo <= c * 2048 + i < hi for lo, hi in rng):
                continue
            k = K[d + i]
            o = O[d + i]
            if k != o and ram[c * 2048 + i] == k:
                ram[c * 2048 + i] = o
                npoke += 1
    print(f"{label}: 청크 {chunks} 중 디스크 대응 {nmap}, 되돌린 바이트 {npoke}")
    return bytes(ram)


def main():
    src, kbin, obin, out = sys.argv[1:5]
    only = sys.argv[5] if len(sys.argv) > 5 else None            # 선택: BaseRAM|CDRAM|SysCardRAM 만 되돌림
    rng = None
    if len(sys.argv) > 6:                                        # 선택: 그 도메인 안의 RAM 오프셋 범위 lo:hi[,lo:hi...] (hex)
        rng = [(int(lo, 16), int(hi, 16)) for lo, hi in (s.split(':') for s in sys.argv[6].split(','))]
    raw = unrzip(Path(src).read_bytes())
    assert raw[:7] == b"RASTATE", raw[:8]
    # RASTATE 블록: id(4) + size(4) + data
    pos = 8
    mem_off = mem_len = None
    while pos + 8 <= len(raw):
        bid = raw[pos:pos + 4]
        size = struct.unpack_from("<I", raw, pos + 4)[0]
        pos += 8
        if bid == b"MEM ":
            mem_off, mem_len = pos, size
            break
        pos += size
    assert mem_off is not None
    mem = raw[mem_off:mem_off + mem_len]
    assert mem[:8] == b"MDFNSVST"
    K = data_track(kbin)
    O = data_track(obin)
    assert len(K) == len(O)
    buf = bytearray(raw)
    for sec, fld, off, ln in find_sections(mem):
        if (sec, fld) in (("MAIN", "BaseRAM"), ("HuC", "CDRAM"), ("HuC", "SysCardRAM")):
            if only and fld != only:
                continue
            new = revert(mem[off:off + ln], K, O, f"{sec}.{fld}", rng)
            buf[mem_off + off:mem_off + off + ln] = new
    Path(out).write_bytes(bytes(buf))
    print("wrote", out, len(buf))


if __name__ == "__main__":
    main()
