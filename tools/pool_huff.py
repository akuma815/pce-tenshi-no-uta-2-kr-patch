#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카드 상주 대사 풀 — 사전(BPE) + 정준 허프만 부호화 (256KB 카드 2단계, 2026-10-11).

기호 값(16비트):
  0x0000            = 레코드/사전 항목 끝(EOS, 원문 NUL)
  0x00XX (XX≠0)     = 1바이트 원문 문자(제어 코드 등)
  0xLLTT (LL 81-EF) = 2바이트 SJIS 문자(리드 LL, 트레일 TT) — 디코더가 리드를 먼저 내고 트레일은 다음 호출에
  0xF000 + d        = 사전 항목 d (그 자체가 같은 부호로 부호화된 문자열, 중첩 없음)
비트 순서 = 바이트 MSB 부터(디코더: ASL BITBUF → 캐리). 레코드·사전 항목은 바이트 경계에서 시작.
정준 허프만(최대 16비트): 디코딩은 zlib puff 방식 — code |= bit; if code - count[len] < first → symbol[index + code - first].
"""
from __future__ import annotations

import collections
import heapq

import pool_dict_compress as pdc

MAXLEN = 16
EOS = 0x0000
DICT_BASE = 0xF000


def _lengths(freq: dict) -> dict:
    if len(freq) == 1:
        return {next(iter(freq)): 1}
    h = [(f, i, (s,)) for i, (s, f) in enumerate(sorted(freq.items(), key=lambda kv: (kv[1], kv[0])))]
    heapq.heapify(h)
    depth = collections.Counter(); n = len(h)
    while len(h) > 1:
        f1, _, a = heapq.heappop(h); f2, _, b = heapq.heappop(h)
        for s in a + b:
            depth[s] += 1
        heapq.heappush(h, (f1 + f2, n, a + b)); n += 1
    L = {s: min(depth[s], MAXLEN) for s in freq}
    order = sorted(freq, key=lambda s: (freq[s], s))
    while sum(2.0 ** -l for l in L.values()) > 1.0 + 1e-12:
        for s in order:
            if L[s] < MAXLEN:
                L[s] += 1
                break
    return L


def _canonical(L: dict):
    """정준 부호: (길이, 기호값) 순. 반환 counts[0..MAXLEN], symbols(정준 순), codes{sym:(code,len)}."""
    syms = sorted(L, key=lambda s: (L[s], s))
    counts = [0] * (MAXLEN + 1)
    for s in syms:
        counts[L[s]] += 1
    codes, code, prev = {}, 0, 0
    for s in syms:
        l = L[s]
        code <<= (l - prev); prev = l
        codes[s] = (code, l); code += 1
    return counts, syms, codes


def _chars_to_syms(chars: list[bytes]) -> list[int]:
    return [(c[0] << 8 | c[1]) if len(c) == 2 else c[0] for c in chars]


def build(records_hex: list[str], n1: int = 40, np_: int = 4):
    saved = (pdc.N1, pdc.NP)                    # 전역 설정은 빌드 뒤 되돌린다(b36 단계가 같은 모듈을 쓴다)
    pdc.N1, pdc.NP = n1, np_
    try:
        res = pdc.build(records_hex)
    finally:
        pdc.N1, pdc.NP = saved
    uniq = sorted(set(records_hex))
    # 사전 항목 번호: tokens1 + groups 를 통틀어 결정적으로
    entries = sorted({e for e in res["tokens1"].values()} | {e for g in res["groups"].values() for e in g})
    did = {e: i for i, e in enumerate(entries)}
    t1, gr = res["tokens1"], res["groups"]

    def rec_syms(h: str) -> list[int]:
        d = bytes.fromhex(res["comp"][h]); out, i = [], 0
        while True:
            b = d[i]
            if b == 0:
                out.append(EOS); return out
            if b in t1:
                out.append(DICT_BASE + did[t1[b]]); i += 1
            elif b in gr:
                out.append(DICT_BASE + did[gr[b][d[i + 1] - 1]]); i += 2
            elif 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
                out.append(b << 8 | d[i + 1]); i += 2
            else:
                out.append(b); i += 1

    rsyms = {h: rec_syms(h) for h in uniq}
    dsyms = [_chars_to_syms(pdc.chars(e)) + [EOS] for e in entries]
    freq = collections.Counter(s for q in rsyms.values() for s in q)
    for q in dsyms:
        freq.update(q)
    assert max(freq) < 0x10000 and all(s < DICT_BASE or s - DICT_BASE < 0x1000 for s in freq)
    L = _lengths(freq)
    counts, symbols, codes = _canonical(L)

    def pack(q: list[int]) -> bytes:
        bits, nb, out = 0, 0, bytearray()
        for s in q:
            c, l = codes[s]
            bits = (bits << l) | c; nb += l
            while nb >= 8:
                nb -= 8; out.append((bits >> nb) & 0xFF)
        if nb:
            out.append((bits << (8 - nb)) & 0xFF)
        return bytes(out)

    rec_bytes = {h: pack(q) for h, q in rsyms.items()}
    dict_bytes = [pack(q) for q in dsyms]
    model = {"counts": counts, "symbols": symbols}
    for h in uniq:     # 모델 왕복
        assert decode_bytes(rec_bytes[h], model, lambda d: dict_bytes[d]) == bytes.fromhex(h), h[:20]
    return {"counts": counts, "symbols": symbols, "rec": rec_bytes, "dict": dict_bytes,
            "n_dict": len(entries), "maxlen": max(L.values())}


class BitReader:
    def __init__(self, data: bytes):
        self.d, self.i, self.buf, self.cnt = data, 0, 0, 0

    def bit(self) -> int:
        if self.cnt == 0:
            self.buf = self.d[self.i]; self.i += 1; self.cnt = 8
        self.cnt -= 1
        b = (self.buf >> 7) & 1
        self.buf = (self.buf << 1) & 0xFF
        return b


def decode_sym(br: BitReader, model) -> int:
    counts, symbols = model["counts"], model["symbols"]
    code = first = index = 0
    for ln in range(1, MAXLEN + 1):
        code |= br.bit()
        cnt = counts[ln]
        if code - cnt < first:
            return symbols[index + (code - first)]
        index += cnt; first += cnt; first <<= 1; code <<= 1
    raise ValueError("bad code")


def decode_bytes(data: bytes, model, dict_get) -> bytes:
    """디코더 모델 — 출력 바이트열(끝 NUL 포함)."""
    out = bytearray(); br = BitReader(data)
    while True:
        s = decode_sym(br, model)
        if s == EOS:
            out.append(0); return bytes(out)
        if s >= DICT_BASE:
            out += decode_bytes(dict_get(s - DICT_BASE), model, dict_get)[:-1]
        elif s > 0xFF:
            out += bytes((s >> 8, s & 0xFF))
        else:
            out.append(s)
