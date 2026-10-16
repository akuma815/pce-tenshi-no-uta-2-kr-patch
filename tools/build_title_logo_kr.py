#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""타이틀 로고 한글화 — 스프라이트 셀 제자리 교체 (2026-10-09 조사 근거).

근거 (translation/title_probe/):
  · 로고 = 16x16 스프라이트 셀 80개, 화면 격자 x 0..255 / y 15..111, 팔레트 0(녹·금·백) + 2(빨간 II)
  · 전 셀이 디스크에 비압축(ISO 0x7B000~0x7DF80, 0x3E000~0x3ED00) — logo_cells.tsv (vram,pal,x,y,iso)
  · 본문 '天使の詩' 색 인덱스 = 15(백) 7/13/1/14(녹) 12(청회 그림자) 3(암적) / 부제 = 3, 15, (금 10·8 은 장식)
방법: 텍스트 bbox 안의 글자 색 픽셀만 지우고(장식 금색 보존) 한글을 같은 팔레트 인덱스로 그려
셀 바이트(4플레인 × 16행 × 2B = 128B)를 다시 만든다. SATB·팔레트·셀 배치는 무수정.

출력: translation/title_probe/mock_title_kr.png (시안), translation/btrack_title_kr_patches.json (ISO 패치)
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "translation" / "title_probe"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
OUT_PATCH = ROOT / "translation" / "btrack_title_kr_patches.json"

MAIN_TEXT = "천사의 시"
SUB_TEXT = "타천사의 선택"
MAIN_BBOX = (44, 47, 170, 95)      # 지우는 범위(원본 글자). 그리기는 MAIN_PLACE 기준      # 원본 天使の詩 영역 (II 는 x160.. pal2 — 건드리지 않음)
SUB_BBOX = (80, 95, 176, 111)
MAIN_CLEAR = {15, 7, 13, 1, 14, 12, 3, 2, 4, 5, 6}      # 녹·백·청회 + 파란 그림자(2,4,5,6)
MAIN_CLEAR_P2 = {7, 11, 13, 14, 15, 12}                 # II 셀(팔레트 2)에 걸친 詩 오른쪽 획: 녹·백만 (빨강 1-6 보존)
MAIN_P2_XMAX = 176
# 사용자 요구(2026-10-09): 글자 높이 = II(y 57..88 = 32px), 텍스트+II 그룹을 금색 테두리 중앙에.
# II 는 x 177..207 고정 → 그룹 중앙 128 이면 텍스트 왼쪽 = 49, 간격 8 → 텍스트 x 49..169
MAIN_PLACE = (49, 57, 169, 89)     # 글자 bbox 목표 (폭 120, 높이 32)
SUB_CLEAR_P2 = {15, 6, 12}
SUB_CLEAR = {3, 15, 12, 11}
# 디자인 색(팔레트 0 인덱스)
OUTLINE_MAIN, SHADOW_MAIN = 15, 12
GRAD_MAIN = [14, 14, 1, 1, 1, 7, 7, 7, 13, 13]      # 위→아래 비율로 샘플
FILL_SUB, OUTLINE_SUB = 15, 3

FONT_MAIN = Path("C:/Windows/Fonts/KoPubDotumBold.ttf")
FONT_SUB = Path("C:/Windows/Fonts/KoPubDotumBold.ttf")


def load_pal():
    pal = (D / "pal_f2700.bin").read_bytes()
    def rgb(i):
        w = pal[2 * i] | (pal[2 * i + 1] << 8)
        B, R, G = w & 7, (w >> 3) & 7, (w >> 6) & 7
        return (R * 255 // 7, G * 255 // 7, B * 255 // 7)
    return rgb


def cell_decode(buf: bytes) -> list[list[int]]:
    def wd(o): return buf[o] | (buf[o + 1] << 8)
    px = [[0] * 16 for _ in range(16)]
    for y in range(16):
        w = y * 2
        for x in range(16):
            m = 1 << (15 - x)
            px[y][x] = ((wd(w) & m) > 0) | (((wd(32 + w) & m) > 0) << 1) \
                | (((wd(64 + w) & m) > 0) << 2) | (((wd(96 + w) & m) > 0) << 3)
    return px


def cell_encode(px: list[list[int]]) -> bytes:
    out = bytearray(128)
    for y in range(16):
        words = [0, 0, 0, 0]
        for x in range(16):
            c = px[y][x]
            for p in range(4):
                if (c >> p) & 1:
                    words[p] |= 1 << (15 - x)
        for p in range(4):
            o = p * 32 + y * 2
            out[o] = words[p] & 0xFF
            out[o + 1] = words[p] >> 8
    return bytes(out)


def render_text(text, font_path, size, box_w, box_h):
    """글자를 넉넉한 캔버스에 렌더해 **실제 픽셀 bbox 로 잘라** box 중앙에 놓는다.
    (2026-10-09 수정: 좁은 캔버스에 중앙 정렬 후 crop 하면 양끝이 잘린 채 '맞는' 것으로
    판정돼 '시' 의 ㅣ 가 사라졌다 — 실제 bbox 가 box 보다 크면 None 을 돌려준다.)"""
    font = ImageFont.truetype(str(font_path), size)
    big = Image.new("L", (box_w * 4 + 64, box_h * 4 + 64), 0)
    ImageDraw.Draw(big).text((32, 32), text, fill=255, font=font)
    bb = big.getbbox()
    if not bb:
        return None
    glyph = big.crop(bb)
    if glyph.width > box_w or glyph.height > box_h:
        return None
    out = Image.new("L", (box_w, box_h), 0)
    out.paste(glyph, ((box_w - glyph.width) // 2, (box_h - glyph.height) // 2))
    return out


def dilate(mask, r=1):
    w, h = mask.size
    src = mask.load()
    out = Image.new("L", (w, h), 0)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            if src[x, y] > 127:
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        if 0 <= x + dx < w and 0 <= y + dy < h:
                            dst[x + dx, y + dy] = 255
    return out


def paint_main(canvas, bbox):
    px0, py0, px1, py1 = MAIN_PLACE
    tw, th = px1 - px0, py1 - py0
    # 높이 th 에 가장 가까운 글리프 높이의 폰트 크기 → 폭이 넘치면 가로만 축소(원본도 장체)
    font_best = None
    for size in range(th + 12, 8, -1):
        font = ImageFont.truetype(str(FONT_MAIN), size)
        big = Image.new("L", (600, 200), 0)
        ImageDraw.Draw(big).text((20, 20), MAIN_TEXT, fill=255, font=font)
        bb = big.getbbox()
        if bb and bb[3] - bb[1] <= th:
            font_best = (size, big.crop(bb))
            break
    assert font_best is not None
    glyph = font_best[1]
    if glyph.width > tw:
        glyph = glyph.resize((tw, glyph.height), Image.LANCZOS).point(lambda v: 255 if v >= 110 else 0)
    w, h = tw + 4, th + 4
    fill = Image.new("L", (w, h), 0)
    fill.paste(glyph, (2 + (tw - glyph.width) // 2, 2 + (th - glyph.height) // 2))
    outline = dilate(fill, 1)
    shadow = Image.new("L", (w, h), 0); shadow.paste(outline, (1, 1))
    fp, op, sp = fill.load(), outline.load(), shadow.load()
    fb = fill.getbbox()
    ox, oy = px0 - 2, py0 - 2
    for y in range(h):
        for x in range(w):
            if sp[x, y] > 127 and op[x, y] <= 127:
                canvas[(ox + x, oy + y)] = SHADOW_MAIN
    for y in range(h):
        for x in range(w):
            if op[x, y] > 127:
                canvas[(ox + x, oy + y)] = OUTLINE_MAIN
    for y in range(h):
        for x in range(w):
            if fp[x, y] > 127:
                t = (y - fb[1]) / max(1, (fb[3] - fb[1] - 1))
                canvas[(ox + x, oy + y)] = GRAD_MAIN[min(len(GRAD_MAIN) - 1, int(t * len(GRAD_MAIN)))]


def paint_sub(canvas, bbox):
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    best = None
    for size in range(h, 8, -1):
        m = render_text(SUB_TEXT, FONT_SUB, size, w - 4, h - 3)
        if m is not None:
            best = m
            break
    fill = Image.new("L", (w, h), 0); fill.paste(best, (2, 1))
    outline = dilate(fill, 1)
    fp, op = fill.load(), outline.load()
    for y in range(h):
        for x in range(w):
            if op[x, y] > 127:
                canvas[(x0 + x, y0 + y)] = OUTLINE_SUB
    for y in range(h):
        for x in range(w):
            if fp[x, y] > 127:
                canvas[(x0 + x, y0 + y)] = FILL_SUB


def main() -> None:
    rgb = load_pal()
    iso = ISO.read_bytes()
    rows = list(csv.DictReader((D / "logo_cells.tsv").open(encoding="utf-8"), delimiter="\t"))
    cells = [r for r in rows if r["pal"] in ("0", "2") and 15 <= int(r["y"]) <= 111 and r["iso"] != "-"]
    # 1) 원본 셀 → 화면 좌표 캔버스 (인덱스), 텍스트 bbox 안 글자색 제거
    canvas: dict[tuple[int, int], int] = {}
    owner: dict[tuple[int, int], str] = {}
    owner_pal: dict[tuple[int, int], str] = {}
    for r in cells:
        off = int(r["iso"], 16)
        px = cell_decode(iso[off:off + 128])
        x0, y0 = int(r["x"]), int(r["y"])
        for y in range(16):
            for x in range(16):
                X, Y = x0 + x, y0 + y
                c = px[y][x]
                owner[(X, Y)] = r["iso"]
                owner_pal[(X, Y)] = r["pal"]
                if r["pal"] == "2":
                    if X < MAIN_P2_XMAX and MAIN_BBOX[1] <= Y < MAIN_BBOX[3] and c in MAIN_CLEAR_P2:
                        c = 0
                    if SUB_BBOX[0] <= X < SUB_BBOX[2] and SUB_BBOX[1] <= Y < SUB_BBOX[3] and c in SUB_CLEAR_P2:
                        c = 0
                elif MAIN_BBOX[0] <= X < MAIN_BBOX[2] and MAIN_BBOX[1] <= Y < MAIN_BBOX[3] and c in MAIN_CLEAR:
                    c = 0
                if SUB_BBOX[0] <= X < SUB_BBOX[2] and SUB_BBOX[1] <= Y < SUB_BBOX[3] and c in SUB_CLEAR:
                    c = 0
                canvas[(X, Y)] = c
    # 2) 한글 그리기
    paint_main(canvas, MAIN_BBOX)
    paint_sub(canvas, SUB_BBOX)
    # 3) 셀 재인코딩 → 패치
    patches = []
    changed_px = 0
    for r in cells:
        off = int(r["iso"], 16)
        old = iso[off:off + 128]
        x0, y0 = int(r["x"]), int(r["y"])
        px = [[canvas.get((x0 + x, y0 + y), 0) for x in range(16)] for y in range(16)]
        if r["pal"] == "2":
            # 새로 그린 글자 픽셀(pal0 인덱스)만 pal2 최근접 색으로 변환. 원본 유지 픽셀은 그대로.
            orig = cell_decode(old)
            def near2(c0):
                tr = rgb(256 + c0)
                return min(range(1, 16), key=lambda k: sum((a - b) ** 2 for a, b in zip(rgb(256 + 32 + k), tr)))
            px = [[(near2(px[y][x]) if (px[y][x] and px[y][x] != orig[y][x]) else px[y][x]) for x in range(16)] for y in range(16)]
        new = cell_encode(px)
        if new != old:
            patches.append({"iso_off": off, "old_hex": old.hex().upper(), "new_hex": new.hex().upper(),
                            "id": f"title@{off:07X}", "mode": "bytes"})
            changed_px += sum(1 for a, b in zip(cell_decode(old), px) for u, v in zip(a, b) if u != v)
    OUT_PATCH.write_text(json.dumps({"format": "BTRACK-TITLE-KR-PATCHES",
                                     "note": "타이틀 로고 스프라이트 셀 제자리 교체 (tools/build_title_logo_kr.py)",
                                     "patches": patches}, ensure_ascii=False, indent=1), encoding="utf-8")
    # 4) 시안: 스크린샷 위에 합성 (셀 범위 전체를 캔버스로 다시 그림)
    shot = Image.open(D / "shot_f2700.png").convert("RGB")
    sp = shot.load()
    for (X, Y), c in canvas.items():
        if 0 <= X < shot.width and 0 <= Y < shot.height:
            if c:
                sp[X, Y] = rgb(256 + (2 if owner_pal.get((X, Y)) == "2" else 0) * 16 + c)
            else:
                # 지워진 글자 자리는 배경(BAT) 색으로 — 원본 스크린샷에서 글자가 아니던 픽셀은 그대로,
                # 글자였던 픽셀은 주변 하늘색으로 근사
                pass
    # 지운 자리를 하늘색으로: 원본 캔버스에서 글자색이던 픽셀 중 새 캔버스가 0 인 곳
    for r in cells:
        off = int(r["iso"], 16)
        px = cell_decode(iso[off:off + 128])
        x0, y0 = int(r["x"]), int(r["y"])
        for y in range(16):
            for x in range(16):
                X, Y = x0 + x, y0 + y
                if px[y][x] and canvas.get((X, Y), 0) == 0:
                    sp[X, Y] = (0, 72, 255)
    shot = shot.resize((shot.width * 3, shot.height * 3), Image.NEAREST)
    shot.save(D / "mock_title_kr.png")
    print(json.dumps({"cells_total": len(cells), "cells_changed": len(patches), "pixels_changed": changed_px,
                      "patch": OUT_PATCH.name, "mock": "translation/title_probe/mock_title_kr.png"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
