#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""컷신 자막 PoC (2026-10-14): 자막 2줄 → 32x32 스프라이트 6개(16x16 패턴 24개) 패턴 데이터.
글리프 = 카드의 실제 EX_GETFNT 12x12 출력(huc_mini_emu) — 게임 본문과 같은 글꼴. 흰 글자(색 1) + 검은 테두리(색 2), 색 0 = 투명.
배치 = 192x32 상자, 줄마다 가운데 정렬, 글자 간격 12px(공백 6px). 출력 = VRAM 워드 순서(리틀엔디언) 바이너리 + 미리보기 PNG.
사용: python -X utf8 tools/make_cutscene_sub_sprites.py <card> <out.bin> <out.png> "<줄1>" "<줄2>"
"""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from huc_mini_emu import ex_getfnt

W, H, NSPR = 192, 32, 6
ASG = json.loads((ROOT / "translation" / "btrack_slot_assignment.json").read_text(encoding="utf-8"))["assignment"]
PUNCT = {"!": "！", "?": "？", ",": "、", ".": "．", "…": "・・・"}


def code_of(ch):
    if 0xAC00 <= ord(ch) <= 0xD7A3:
        if ch not in ASG:
            raise SystemExit(f"미배정 음절: {ch}")
        return int(ASG[ch]["sjis"], 16)
    b = ch.encode("shift_jis")
    return b[0] << 8 | b[1]


def render_line(card, text):
    text = "".join(PUNCT.get(c, c) for c in text)
    cols = []   # (x, 12x12 bitmap rows)
    x = 0
    for ch in text:
        if ch == " ":
            x += 6
            continue
        a, g = ex_getfnt(card, code_of(ch), 1)
        assert a == 0, (ch, a)
        rows = [g[2 * r] << 8 | g[2 * r + 1] for r in range(12)]
        cols.append((x, rows))
        x += 12
    return cols, x


def main():
    cardp, outb, outp, l1, l2 = sys.argv[1:6]
    card = Path(cardp).read_bytes()
    if len(card) % 0x2000 == 512:
        card = card[512:]
    pix = [[0] * W for _ in range(H)]
    for li, text in enumerate((l1, l2)):
        cols, width = render_line(card, text)
        assert width <= W - 2, f"줄이 상자보다 김: {width}px > {W - 2}"
        x0 = (W - width) // 2
        y0 = 2 + li * 15
        for x, rows in cols:
            for r, bits in enumerate(rows):
                for c in range(12):
                    if bits >> (15 - c) & 1:
                        pix[y0 + r][x0 + x + c] = 1
    # 테두리(8방향)
    for y in range(H):
        for x in range(W):
            if pix[y][x] == 0 and any(0 <= y + dy < H and 0 <= x + dx < W and pix[y + dy][x + dx] == 1
                                      for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                pix[y][x] = 2
    # 패턴: 스프라이트 s(32x32) = 패턴 4s+0 좌상, +1 우상, +2 좌하, +3 우하. 패턴 = 4평면 × 16줄 워드(비트15 = 맨 왼쪽)
    out = bytearray()
    for s in range(NSPR):
        for q in range(4):
            ox = s * 32 + (q & 1) * 16
            oy = (q >> 1) * 16
            for plane in range(4):
                for r in range(16):
                    w = 0
                    for c in range(16):
                        if pix[oy + r][ox + c] >> plane & 1:
                            w |= 1 << (15 - c)
                    out += bytes((w & 0xFF, w >> 8))
    Path(outb).write_bytes(out)
    from PIL import Image
    im = Image.new("RGB", (W, H), (60, 90, 160))
    for y in range(H):
        for x in range(W):
            if pix[y][x]:
                im.putpixel((x, y), (255, 255, 255) if pix[y][x] == 1 else (0, 0, 0))
    im.resize((W * 3, H * 3), Image.NEAREST).save(outp)
    print(outb, len(out), "bytes")


if __name__ == "__main__":
    main()
