#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제자리 패치 오탐 감사 (2026-10-12): 그래픽·코드 같은 바이너리 안의 우연한 바이트열을 텍스트로 보고 번역한 곳 찾기.
계기: 0xC890D1 「7E C7 B4 00」 을 몬스터명 「ヌエ」(반각 ﾇｴ)로, 0x10BA4F5 「D2 D3 00」 을 「メモ」로 보고 번역 → 첫 컷신 그래픽 깨짐(사용자 퀵세이브 3).
방법: 빌드 디스크와 원본의 차이 구간마다 원본 앞뒤 64바이트의 「텍스트다움」(SJIS 2바이트 쌍·제어·00 비율)을 재고, 낮은 구간을 색인 행과 함께 출력.
사용: python -X utf8 tools/audit_binary_patches.py <빌드 태그>
"""
import csv, io, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
tag = sys.argv[1]; sys.argv = ["x"]
from build_btrack_b7_hook_build import T2
import numpy as np

o = (ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin").read_bytes()[T2:]
k = (ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{tag}.bin").read_bytes()[T2:]
n = min(len(o), len(k))
d = np.nonzero(np.frombuffer(o[:n], np.uint8) != np.frombuffer(k[:n], np.uint8))[0]
spans = []
for i in d:
    i = int(i)
    if spans and i <= spans[-1][1] + 16:
        spans[-1][1] = i
    else:
        spans.append([i, i])
raw = (ROOT / "translation" / "ziria_z8_text_entry_index.csv").read_bytes().decode("utf-8-sig")
idx = {}
for r in csv.DictReader(io.StringIO(raw, newline="")):
    if r["iso_offset"]:
        idx.setdefault(int(r["iso_offset"], 16), r)


def textiness(b: bytes) -> float:
    """SJIS 2바이트 문자·ASCII 제어(00-1F)·반각 공백 7E 가 차지하는 바이트 비율."""
    ok = i = 0
    while i < len(b):
        x = b[i]
        if (0x81 <= x <= 0x9F or 0xE0 <= x <= 0xEF) and i + 1 < len(b) and 0x40 <= b[i + 1] <= 0xFC:
            ok += 2; i += 2; continue
        if x < 0x20 or x == 0x7E:
            ok += 1
        i += 1
    return ok / max(1, len(b))


KNOWN = [(0xBEB000, 0xBF3000, "카드 미니게임 타일(b29 의도)"), (0xBD6CBC, 0xBD6CBE, "카드 게임 종료 재무장 훅(b30 의도)")]
rows = []
for s, e in spans:
    if any(lo <= s < hi for lo, hi, _ in KNOWN):
        continue
    ctx = o[max(0, s - 64):s] + o[e + 1:e + 65]
    t = textiness(ctx)
    near = [r for off, r in idx.items() if s - 8 <= off <= e]
    rows.append((t, s, e, near))
rows.sort()
print(f"{tag}: 차이 구간 {len(spans)} (알려진 의도 구간 제외 {len(rows)})")
for t, s, e, near in rows:
    if t >= 0.6:
        break
    lab = "; ".join(f"{r['id']} {r['subcategory']} {r['original']}→{r['translation']}" for r in near[:2])
    print(f"텍스트다움 {t:.2f} {s:#09x}-{e:#09x} ({e - s + 1}B) 원본 {o[s:e + 1][:12].hex(' ')} | {lab}")
