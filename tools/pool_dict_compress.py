#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카드 상주 텍스트 풀 사전 압축 (b36 — ares 호환: 카드를 512KB 로 줄이기 위해).

배경: ares 의 Super System Card 보드는 카드 ROM 을 뱅크 $00-$3F(512KB)만 매핑한다(ares/pce/cartridge/board/
super-system-card.cpp). b35 까지의 768KB 카드는 텍스트 $20-$3F·$44, 인덱스 $45-$50, 훅 뱅크 $5F 를 써서 ares 에서는
새 게임 직후 깨졌다. 풀 텍스트 266KB 를 사전 토큰으로 줄여 $20-$3F 안에 텍스트·인덱스·사전·훅 뱅크를 모두 넣는다.

토큰 = 풀 텍스트 어디에도(어느 위치에도) 나오지 않는 바이트 값. 리더(카드 serve 디코더)가 엔진에 넘기기 전에 펼치므로
엔진·렌더러가 보는 바이트열은 압축 전과 같다.
  · 1바이트 토큰 v        → 사전 항목 하나
  · 접두 p + 색인 i(1..255) → 그룹 p 의 i 번째 항목 (색인 0 은 쓰지 않는다: 풀 레코드 내부 00 금지)
사전 항목 = 원문 문자(2바이트 SJIS 또는 1바이트 제어) 2개 이상의 연속, NUL 종료, 토큰 없음(중첩 없음).
"""
from __future__ import annotations

import collections

N1 = 40            # 1바이트 토큰 수
NP = 10            # 접두 수 (그룹당 255 항목)
MAXN = 8           # 사전 항목 최대 문자 수


def chars(d: bytes) -> list[bytes]:
    i, out = 0, []
    while i < len(d):
        b = d[i]
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            out.append(d[i:i + 2]); i += 2
        else:
            out.append(d[i:i + 1]); i += 1
    return out


def _blen(t) -> int:
    return sum(len(c) for c in t)


def _parse(s, dic):
    """DP 최소 바이트 분해. dic: 문자 튜플 → 토큰 비용(1/2). 반환 (비용, [(i, n, 튜플|None)])."""
    L = len(s); INF = 1 << 30
    best = [0] + [INF] * L; how = [None] * (L + 1)
    for i in range(L):
        bi = best[i]
        c = bi + len(s[i])
        if c < best[i + 1]:
            best[i + 1] = c; how[i + 1] = (i, None)
        for n in range(2, min(MAXN, L - i) + 1):
            t = s[i:i + n]
            k = dic.get(t)
            if k is not None and bi + k < best[i + n]:
                best[i + n] = bi + k; how[i + n] = (i, t)
    steps, j = [], L
    while j > 0:
        i, t = how[j]; steps.append((i, j - i, t)); j = i
    steps.reverse()
    return best[L], steps


def build(records_hex: list[str], particle_bytes: bytes = b""):
    """records_hex: 유니크 풀 레코드(NUL 종료 hex). 반환 dict:
    tokens1 {값: 항목 bytes}, groups {접두: [항목 bytes...] (색인 1부터)}, comp {원 hex: 압축 hex}."""
    uniq = sorted(set(records_hex))
    raw = [bytes.fromhex(h) for h in uniq]
    seen = set(particle_bytes)
    for d in raw:
        assert d[-1] == 0 and 0 not in d[:-1]
        seen |= set(d)
    free = [v for v in range(1, 256) if v not in seen]
    assert len(free) >= N1 + NP, f"토큰용 빈 바이트 값 {len(free)} < {N1 + NP}"
    t1_vals, pre_vals = free[:N1], free[N1:N1 + NP]
    seqs = [tuple(chars(d[:-1])) for d in raw]
    cnt = collections.Counter()
    for s in seqs:
        L = len(s)
        for i in range(L):
            for n in range(2, MAXN + 1):
                if i + n > L:
                    break
                cnt[s[i:i + n]] += 1
    cand = [(t, c) for t, c in cnt.items() if c >= 3 and _blen(t) >= 3]
    cand.sort(key=lambda x: (-(x[1] * (_blen(x[0]) - 2) - _blen(x[0])), b"".join(x[0])))
    cap = N1 + NP * 255
    sel = [t for t, _ in cand[:cap]]
    for _ in range(4):
        dic = {t: 2 for t in sel}
        use = collections.Counter()
        for s in seqs:
            use.update(t for _, _, t in _parse(s, dic)[1] if t)
        sv = {t: use[t] * (_blen(t) - 2) - (_blen(t) + 3) for t in sel}
        keep = sorted((t for t in sel if sv[t] > 0), key=lambda t: (-sv[t], b"".join(t)))[:cap]
        ks = set(keep)
        sel = keep + [t for t, _ in cand if t not in ks][:cap - len(keep)]
    dic = {t: 2 for t in sel}
    use = collections.Counter()
    for s in seqs:
        use.update(t for _, _, t in _parse(s, dic)[1] if t)
    order = sorted((t for t in sel if use[t]), key=lambda t: (-use[t] * (_blen(t) - 1), b"".join(t)))
    tier1 = order[:N1]
    for t in tier1:
        dic[t] = 1
    # 최종 분해 → 실제 쓰이는 2바이트 항목만 그룹 배정
    use = collections.Counter()
    for s in seqs:
        use.update(t for _, _, t in _parse(s, dic)[1] if t)
    tier2 = sorted((t for t in dic if dic[t] == 2 and use[t]), key=lambda t: (-use[t], b"".join(t)))[:NP * 255]
    code: dict[tuple, bytes] = {}
    tokens1 = {}
    for v, t in zip(t1_vals, tier1):
        code[t] = bytes((v,)); tokens1[v] = b"".join(t)
    groups = {p: [] for p in pre_vals}
    for k, t in enumerate(tier2):
        p = pre_vals[k // 255]
        groups[p].append(b"".join(t))
        code[t] = bytes((p, len(groups[p])))
    final = {t: len(code[t]) for t in code}
    comp = {}
    for h, s in zip(uniq, seqs):
        out = bytearray()
        for i, n, t in _parse(s, final)[1]:
            out += code[t] if t else s[i]
        out.append(0)
        comp[h] = bytes(out).hex().upper()
    groups = {p: g for p, g in groups.items() if g}
    res = {"tokens1": tokens1, "groups": groups, "comp": comp}
    for h in uniq:
        assert expand(bytes.fromhex(comp[h]), res) == bytes.fromhex(h), f"왕복 실패 {h[:24]}"
    return res


def expand(d: bytes, res) -> bytes:
    """디코더 모델 (카드 serve 와 같은 규칙): 토큰 값은 위치와 무관하게 토큰."""
    t1, gr = res["tokens1"], res["groups"]
    out, i = bytearray(), 0
    while True:
        b = d[i]
        if b == 0:
            return bytes(out) + b"\x00"
        if b in t1:
            out += t1[b]; i += 1
        elif b in gr:
            out += gr[b][d[i + 1] - 1]; i += 2
        else:
            out.append(b); i += 1
