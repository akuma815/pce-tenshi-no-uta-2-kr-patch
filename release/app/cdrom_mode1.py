# -*- coding: utf-8 -*-
"""CD-ROM Mode 1 raw 섹터(2352B) 생성: sync + header(MSF BCD, mode 1) + 2048 data + EDC + 8 zero + ECC(P/Q).
알고리즘은 ECM(Neill Corlett) 과 동일. cooked(2048B) 데이터와 절대 LBA 만 있으면 raw 를 재구성한다."""

SYNC = b"\x00" + b"\xFF" * 10 + b"\x00"

_edc_lut = []
for _i in range(256):
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if (_e & 1) else 0)
    _edc_lut.append(_e)

_f_lut = [0] * 256
_b_lut = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if (_i & 0x80) else 0)) & 0xFF
    _f_lut[_i] = _j
    _b_lut[_i ^ _j] = _i


def edc_compute(data):
    e = 0
    lut = _edc_lut
    for b in data:
        e = (e >> 8) ^ lut[(e ^ b) & 0xFF]
    return e


def _ecc_block(src, major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    out = bytearray(major_count * 2)
    f, bl = _f_lut, _b_lut
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = 0
        b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = f[a]
        a = bl[f[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b
    return bytes(out)


def lba_to_msf_bcd(lba):
    a = lba + 150
    m, s, f = a // 4500, (a // 75) % 60, a % 75
    bcd = lambda v: ((v // 10) << 4) | (v % 10)
    return bytes((bcd(m), bcd(s), bcd(f)))


def mode1_sector(data2048, lba):
    """cooked 2048B + 절대 LBA → raw 2352B."""
    if len(data2048) != 2048:
        raise ValueError("data must be 2048 bytes")
    head = SYNC + lba_to_msf_bcd(lba) + b"\x01"
    body = head + data2048
    edc = edc_compute(body).to_bytes(4, "little")
    pre = bytearray(body + edc + b"\x00" * 8)          # 2076 B: 0..0x81B
    p = _ecc_block(pre[0x0C:], 86, 24, 2, 86)           # 172 B
    q_src = bytes(pre[0x0C:]) + p                      # 2064 + 172 = 2236
    q = _ecc_block(q_src, 52, 43, 86, 88)               # 104 B
    return bytes(pre) + p + q


def raw_to_cooked(raw, first=0):
    n = len(raw) // 2352
    return b"".join(raw[i * 2352 + 16:i * 2352 + 2064] for i in range(first, n))


def cooked_to_raw(cooked, lba0, progress=None):
    n = len(cooked) // 2048
    out = bytearray()
    for i in range(n):
        out += mode1_sector(cooked[i * 2048:(i + 1) * 2048], lba0 + i)
        if progress and (i & 255) == 0:
            progress(i / n)
    return bytes(out)
