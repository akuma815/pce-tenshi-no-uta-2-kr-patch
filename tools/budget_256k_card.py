#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""256KB 시스템 카드 유지 방안 — 정확 예산 산출 (드라이런, 게임 파일 무변경).

가정(설계안 2026-10-11, HANDOFF §'256KB 카드 유지 방안 검토'):
  · BIOS EX_GETFNT 패치: 12x12 글리프를 '쓰는 것만' 압축 배치(인덱스 → 압축 번호는 비트맵 + 순위표),
    16x16 요청은 말풍선 음절·기호만 별도 16x16 으로, 나머지는 12x12 경로로 돌린다 → 16x16 폰트 영역(0x10000-0x2BFFF) 전부 회수.
  · 대사 풀: 사전(BPE) 토큰 + 정준 허프만 비트스트림. 레코드 시작은 바이트 정렬, 8KB 뱅크 경계 불가침.
  · 인덱스: 씬별 24 버킷, 항목 = 오프셋 델타(1B, 0xFF+2B 탈출) + 레코드 번호(2B). 레코드 표(번호 → 뱅크 내 오프셋 13비트 + 원문 길이-1 10비트 = 3B,
    뱅크는 번호 구간표). 원문 길이가 둘 이상인 레코드는 번호를 복제.
출력: 항목별 바이트 수와 뱅크 배치 시뮬레이션 결과(들어가는지/여유).
"""
from __future__ import annotations

import collections
import heapq
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
_argv = sys.argv; sys.argv = ["x"]
import build_btrack_b9_hook_build as b9
import analyze_system_card_font_slots as fs
import pool_dict_compress as pdc
sys.argv = _argv

BANK = 0x2000
ORIG_CARD = Path(r"H:\BizHawk\Firmware\PCECD_3.0-(J).pce")
MAXLEN = 16


def huff_lengths(freq: dict, limit: int = MAXLEN) -> dict:
    """길이 제한 허프만 (단순: 허프만 후 초과 길이를 Kraft 합 보정)."""
    if len(freq) == 1:
        return {next(iter(freq)): 1}
    h = [(f, i, (s,)) for i, (s, f) in enumerate(sorted(freq.items(), key=lambda kv: (kv[1], repr(kv[0]))))]
    heapq.heapify(h)
    depth = collections.Counter()
    cnt = len(h)
    while len(h) > 1:
        f1, _, a = heapq.heappop(h); f2, _, b = heapq.heappop(h)
        for s in a + b:
            depth[s] += 1
        heapq.heappush(h, (f1 + f2, cnt, a + b)); cnt += 1
    L = {s: min(depth[s], limit) for s in freq}
    # Kraft 보정: 합 > 1 이면 가장 빈도 낮은(길이 < limit) 것을 늘린다
    order = sorted(freq, key=lambda s: (freq[s], repr(s)))
    while sum(2.0 ** -l for l in L.values()) > 1.0 + 1e-12:
        for s in order:
            if L[s] < limit:
                L[s] += 1
                break
    return L


def parse_symbols(comp: bytes, res) -> list:
    """압축 레코드 → 기호 열 (원문 문자 bytes 또는 ('D', 사전 항목 bytes)). NUL 은 EOS 기호 b'\\x00'."""
    t1, gr = res["tokens1"], res["groups"]
    out, i = [], 0
    while True:
        b = comp[i]
        if b == 0:
            out.append(b"\x00"); return out
        if b in t1:
            out.append(("D", t1[b])); i += 1
        elif b in gr:
            out.append(("D", gr[b][comp[i + 1] - 1])); i += 2
        elif 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            out.append(comp[i:i + 2]); i += 2
        else:
            out.append(comp[i:i + 1]); i += 1


def text_budget(recs_hex, n1, np_, dict_mode):
    pdc.N1, pdc.NP = n1, np_
    res = pdc.build(recs_hex)
    uniq = sorted(set(recs_hex))
    seqs = {h: parse_symbols(bytes.fromhex(res["comp"][h]), res) for h in uniq}
    freq = collections.Counter(s for q in seqs.values() for s in q)
    dict_entries = sorted({s[1] for q in seqs.values() for s in q if isinstance(s, tuple)})
    if dict_mode == "huff":       # 사전 항목도 같은 부호로(문자만) + EOS
        for e in dict_entries:
            for c in pdc.chars(e):
                freq[c] += 1
            freq[b"\x00"] += 1
    L = huff_lengths(freq)
    rec_bytes = {h: (sum(L[s] for s in q) + 7) // 8 for h, q in seqs.items()}
    if dict_mode == "huff":
        dict_bytes = sum((sum(L[c] for c in pdc.chars(e)) + L[b"\x00"] + 7) // 8 for e in dict_entries)
    else:
        dict_bytes = sum(len(e) + 1 for e in dict_entries)
    dict_ptrs = 3 * len(dict_entries)                # 사전 항목 주소(뱅크 구간 + 오프셋) 표
    table = 2 * len(freq) + 4 * (MAXLEN + 1)          # 정준 허프만: 기호값 목록 + 길이별 first/count
    return {"n1": n1, "np": np_, "dict_mode": dict_mode, "records": rec_bytes, "dict_bytes": dict_bytes,
            "dict_ptrs": dict_ptrs, "table": table, "symbols": len(freq), "maxlen": max(L.values()),
            "text_total": sum(rec_bytes.values())}


def index_budget(rec_ids):
    """rec_ids: (scene, key, (hex, lm1)) 목록 → 인덱스 바이트."""
    per = collections.defaultdict(list)
    for lba, key, rid in rec_ids:
        per[lba].append((key, rid))
    total, esc, by_scene = 0, 0, {}
    for lba, ents in per.items():
        t0 = total
        total += 2 + 24 * 2
        buckets = collections.defaultdict(list)
        for key, rid in ents:
            buckets[key >> 13].append(key & 0x1FFF)
        for kb, offs in buckets.items():
            prev = 0
            for o in sorted(offs):
                d = o - prev; prev = o
                total += 1 + 2 + (2 if d >= 255 else 0)
                esc += d >= 255
            total += 1                                  # 버킷 끝
        total += 24 - len(buckets)                      # 빈 버킷도 끝 표지 1B
        by_scene[lba] = total - t0
    return total, esc, by_scene


def font_budget(card_orig: bytes):
    asg = json.loads((ROOT / "translation" / "btrack_slot_assignment.json").read_text(encoding="utf-8"))["assignment"]
    hangul = {fs.glyph_index(tuple(bytes.fromhex(e["sjis"])), card_orig) for e in asg.values()}
    nonkanji = set()
    for lead in range(0x81, 0x88):
        for t in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            i = fs.glyph_index((lead, t), card_orig)
            if i is not None:
                nonkanji.add(i)
    keep12 = hangul | nonkanji
    # 말풍선(16x16) 문자: 카드 미니게임 패치의 새 바이트열에서
    bal = json.loads((ROOT / "translation" / "btrack_b30_card_balloon.json").read_text(encoding="utf-8"))
    codes16 = set()
    for p in bal["patches"]:
        d = bytes.fromhex(p["new_hex"]); i = 0
        while i < len(d):
            if 0x81 <= d[i] <= 0x9F or 0xE0 <= d[i] <= 0xFC:
                codes16.add(d[i:i + 2]); i += 2
            else:
                i += 1
    keep16 = {fs.glyph_index((c[0], c[1]), card_orig) for c in codes16} - {None}
    n_idx = 3640
    rank = (n_idx + 7) // 8 + 2 * ((n_idx + 63) // 64)
    return {"keep12": len(keep12), "bytes12": len(keep12) * 18, "keep16": len(keep16), "bytes16": len(keep16) * 32,
            "rank12": rank, "rank16": rank, "hangul": len(hangul), "nonkanji": len(nonkanji)}


def ffd(items, bins):
    """items: [(이름, 크기)], bins: [(이름, 용량)] → (배치 성공, 남는 바이트 합, 실패 항목)."""
    cap = [[n, c] for n, c in bins]
    fail = []
    for name, size in sorted(items, key=lambda x: -x[1]):
        for b in cap:
            if b[1] >= size:
                b[1] -= size; break
        else:
            fail.append((name, size))
    return not fail, sum(c for _, c in cap), fail


def main():
    card = ORIG_CARD.read_bytes()
    assert len(card) == 256 * 1024
    rows = [(lba, int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little"), r["encoded_hex"], r["original_raw_length"])
            for lba in b9.SCENES_B9 for r in b9.payload(lba)]
    recs_hex = [h for _, _, h, _ in rows]
    rid_set = sorted({(h, ln) for _, _, h, ln in rows})
    best = None
    variants = []
    for n1, np_ in ((40, 10), (40, 4), (40, 0), (20, 10), (0, 0)):
        for dm in ("raw", "huff"):
            t = text_budget(recs_hex, n1, np_, dm)
            tot = t["text_total"] + t["dict_bytes"] + t["dict_ptrs"] + t["table"]
            variants.append((tot, n1, np_, dm, t["text_total"], t["dict_bytes"], t["table"], t["symbols"], t["maxlen"]))
            if best is None or tot < best[0]:
                best = (tot, t)
    for v in sorted(variants):
        print("text variant tot=%d N1=%d NP=%d dict=%s | text=%d dict=%d table=%d syms=%d maxlen=%d" % v)
    t = best[1]
    idx_bytes, esc, idx_by_scene = index_budget([(lba, key, (h, ln)) for lba, key, h, ln in rows])
    rec_table = 3 * len(rid_set)
    f = font_budget(card)
    scene_table = len(b9.SCENES_B9) * 44 + 1
    code = 1600                       # 디코더·armchk·EX_GETFNT 패치·조사·게이트·재무장(추정 상한)
    small = 416 + 64 + 16 + 42 + 64   # 받침 비트표·조사 문자열·서명·행·여유
    print(json.dumps({"font": f, "index_bytes": idx_bytes, "index_escapes": esc, "record_ids": len(rid_set),
                      "record_table": rec_table, "scene_table": scene_table}, ensure_ascii=False))

    # --- 공간: 16x16 영역 전부(뱅크 $08-$15) + 12x12 영역 뱅크 $18-$1F 중 압축 폰트 뒤 + BIOS 영역 FF 런(코드·소형 표용)
    bins = [(f"bank{b:02X}", BANK) for b in range(0x08, 0x16)]
    f12 = f["bytes12"]
    full12, rem12 = divmod(f12, BANK)
    for b in range(0x18 + full12, 0x20):
        bins.append((f"bank{b:02X}", BANK - (rem12 if b == 0x18 + full12 else 0)))
    small_runs = [280, 3966, 902, 186, 1456, 2658]   # 0x1EC4·0x2CF9·0x3C7A·0x5F46·0x7A50·0x2D59E (b7.6 인벤토리, CDL cold)
    for i, n in enumerate(small_runs):
        bins.append((f"run{i}", n))
    items = [(f"rec{i}", n) for i, n in enumerate(sorted(t["records"].values(), reverse=True))]
    items += [("dict", t["dict_bytes"]), ("dict_ptrs", t["dict_ptrs"]), ("huff_table", t["table"]),
              ("record_table_a", rec_table // 2), ("record_table_b", rec_table - rec_table // 2), ("font16", f["bytes16"]), ("rank12", f["rank12"]), ("rank16", f["rank16"]),
              ("scene_table", scene_table), ("code", code), ("small", small)]
    # 인덱스는 씬 단위(씬별 크기)로 배치
    # 인덱스 = 씬 머리(매직 2B + 버킷 포인터 48B) + 고유 버킷 본문(같은 내용의 버킷은 씬끼리 공유 — 포인터만 다름)
    ridmap = {k: i for i, k in enumerate(rid_set)}
    bk = collections.defaultdict(list)
    for lba, key, h, ln in rows:
        bk[(lba, key >> 13)].append((key & 0x1FFF, ridmap[(h, ln)]))
    uniq_b = {}
    for v in bk.values():
        ents = tuple(sorted(v)); prev = 0; n = 1
        for o, _ in ents:
            n += 3 + (2 if o - prev >= 255 else 0); prev = o
        uniq_b[ents] = n
    for lba in idx_by_scene:
        items.append((f"idxhdr{lba}", 50))
    for i, n in enumerate(uniq_b.values()):
        items.append((f"bucket{i}", n))
    items.append(("empty_bucket", 1))
    print(json.dumps({"index_shared": 50 * len(idx_by_scene) + sum(uniq_b.values()) + 1, "unique_buckets": len(uniq_b),
                      "index_unshared": idx_bytes}, ensure_ascii=False))
    ok, slack, fail = ffd(items, bins)
    need = sum(n for _, n in items)
    have = sum(n for _, n in bins)
    print(json.dumps({"best_text": {k: t[k] for k in ("n1", "np", "dict_mode", "text_total", "dict_bytes", "dict_ptrs", "table", "symbols")},
                      "need": need, "have": have, "fits": ok, "slack_after_pack": slack, "unplaced": fail[:5]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
