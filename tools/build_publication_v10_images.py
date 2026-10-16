#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.0 배포 글 이미지 (2026-10-14): 0.3 글과 같은 틀(종류 표시 + 제목 + 설명 + 화면)을 PIL 로 직접 그린다.
01 = 1.0 패처 출력물 Mednafen 실행 캡처, 02 = 제보 화면(수정 전 — 가게 말투·가게 이름·편지 「(0B)」).
사용: python -X utf8 tools/build_publication_v10_images.py <출력 images 폴더>
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "qa" / "release_Tenshi2_KR_v1.0_20261014"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BG = (244, 243, 236); FG = (30, 42, 34); MUTED = (90, 100, 92); GREEN = (22, 90, 52)
F_TAG = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 22)
F_TITLE = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 26)
F_SUB = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 17)
F_CAP = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 18)


def frame_crop(im):
    """사용자 캡처의 창 테두리·제목 표시줄 제거: 가장자리에서 창 색(짙은 남색) 또는 흰색 줄을 걷어 낸다."""
    im = im.convert("RGB"); w, h = im.size
    def is_border(px):
        r, g, b = px
        return (abs(r - 26) < 12 and abs(g - 56) < 12 and abs(b - 91) < 12) or (r > 225 and g > 225 and b > 225)
    def row_border(y):
        return sum(is_border(im.getpixel((x, y))) for x in range(0, w, 4)) > (w // 4) * 0.6
    def col_border(x):
        return sum(is_border(im.getpixel((x, y))) for y in range(0, h, 4)) > (h // 4) * 0.6
    t = 0
    while t < h // 4 and row_border(t): t += 1
    b = h - 1
    while b > h * 3 // 4 and row_border(b): b -= 1
    l = 0
    while l < w // 4 and col_border(l): l += 1
    r = w - 1
    while r > w * 3 // 4 and col_border(r): r -= 1
    return im.crop((l, t, r + 1, b + 1))


def card(tag, title, sub, panels, caption, out, panel_h=420):
    ims = []
    for p in panels:
        im = p if isinstance(p, Image.Image) else Image.open(p).convert("RGB")
        sc = panel_h / im.height
        ims.append(im.resize((round(im.width * sc), panel_h), Image.NEAREST if im.width < 400 else Image.LANCZOS))
    W = max(1260, sum(i.width for i in ims) + 16 * (len(ims) - 1) + 40)
    H = 130 + panel_h + 20
    c = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(c)
    tw = d.textlength(tag, font=F_TAG)
    d.rounded_rectangle((20, 18, 20 + tw + 24, 54), radius=8, fill=GREEN)
    d.text((32, 20), tag, font=F_TAG, fill=(255, 255, 255))
    d.text((20 + tw + 44, 16), title, font=F_TITLE, fill=FG)
    d.text((20, 64), sub, font=F_SUB, fill=MUTED)
    d.text((30, 90), caption, font=F_CAP, fill=GREEN)
    x = 20
    for im in ims:
        c.paste(im, (x, 122)); x += im.width + 16
    c.save(out)
    print(out, c.size)


S = QA / "smoke"; U = QA / "user_reports"
card("실행 캡처", "1.0 패처로 만든 파일을 Mednafen 에서 실행",
     "Mednafen 1.32.1, 단일 bin. 왼쪽 = 기본 코어(pce) 새 게임 첫 대사, 오른쪽 = 고속 코어(pce_fast) 타이틀 화면.",
     [S / "single_pce_0016.png", S / "single_pcefast_0031.png"],
     "패처 출력물 그대로 (2026-10-14)", OUT / "01.png")
card("실행 캡처 · 수정 전", "플레이 중 받은 화면 (1.0 에서 고친 곳)",
     "내부 빌드에서 찍은 수정 전 화면. 왼쪽부터: 가게 이름 오역 / 같은 여관의 인사(존댓말)·작별 인사(반말) / 편지에 「(0B)」가 글자로 찍힘.",
     [frame_crop(Image.open(U / "66.png")), frame_crop(Image.open(U / "68.png")), frame_crop(Image.open(U / "69.png")), frame_crop(Image.open(U / "70.png"))],
     "모두 1.0 에서 수정 (아래 본문)", OUT / "02.png", panel_h=300)
