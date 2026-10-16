#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비주얼 씬 스태프 크레딧 오프라인 렌더 (2026-10-12 제보: 컷신 뒤 제작진 정보가 □/엉뚱한 글자).
크레딧 렌더러(디스크 0x10DE85x 부근)는 문자열을 **항상 2바이트씩** 읽어 $F9/$F8 에 넣고 EX_GETFNT($E060, 모드 $2A82)를 부른다(1바이트 코드 처리 없음).
그 동작을 그대로 따라 카드의 실제 EX_GETFNT(huc_mini_emu)로 글리프를 받아 PNG 로 그린다.
사용: python -X utf8 tools/render_visual_credits.py <bin> <card> <출력 png> [모드 0=16x16]
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
binp, cardp, outp = sys.argv[1:4]
MODE = sys.argv[4] if len(sys.argv) > 4 else "auto"   # auto = 명령 모드 바이트 & 1 (0 = 16x16, 1 = 12x12, b59 실측)
sys.argv = ["x"]
from PIL import Image
from huc_mini_emu import ex_getfnt, Halt
from build_btrack_b7_hook_build import T2

iso = Path(binp).read_bytes()[T2:]
card = Path(cardp).read_bytes()
if len(card) % 0x2000 == 512:
    card = card[512:]
CREDIT = (0x10E30F0, 0x10E3C00)   # 첫 사본(0x10E4xxx 는 같은 내용 사본)


def records(d, lo, hi):
    """크레딧 문자열 명령 = 01 <플래그 00/01> <x> <y> <문자열> 00 (원본 실측: 직함 01 01 30 80 …, 이름 01 00 58 A0 …)."""
    out, i = [], lo
    while i < hi - 5:
        if d[i] == 0x01 and d[i + 1] in (0x00, 0x01) and d[i + 4] >= 0x81:
            j = d.find(bytes(1), i + 4)
            if 0 < j - i - 4 < 64:
                out.append((i, d[i + 4:j], d[i + 1] & 1)); i = j; continue
        i += 1
    return out


cache = {}


def glyph(code, mode):
    if (code, mode) not in cache:
        try:
            a, g = ex_getfnt(card, code, mode)
        except (Halt, AssertionError, Exception) as e:   # 렌더러가 실제로 넘길 수 있는 아무 코드나 들어오므로 실패도 그림으로 남긴다
            g = bytes([0xAA, 0x55] * 16)
        cache[(code, mode)] = g
    return cache[(code, mode)]


recs = [r for r in records(iso, *CREDIT) if len(r[1]) >= 2][:int(__import__('os').environ.get('NREC', '40'))]
W = 16 * 22
img = Image.new("1", (W, 18 * len(recs)), 0)
for row, (off, s, fm) in enumerate(recs):
    mode = fm if MODE == "auto" else int(MODE)
    for c in range(len(s) // 2):   # 렌더러와 같이 2바이트씩
        code = s[2 * c] << 8 | s[2 * c + 1]
        g = glyph(code, mode)
        for y in range(16):
            bits = g[2 * y] << 8 | g[2 * y + 1]
            for x in range(16):
                if bits >> (15 - x) & 1 and c < 22:
                    img.putpixel((c * 16 + x, row * 18 + y), 1)
img.convert("L").point(lambda v: 255 - v).resize((W * 2, 18 * len(recs) * 2), Image.NEAREST).save(outp)
print("records", len(recs), "->", outp)
