# -*- coding: utf-8 -*-
"""Z11 지상검증 2단계 — 원자재로 화면을 재현해 정답 BAT 기하를 역산한다.

입력: translation/z11_probe/gt/{vram.bin, palette.bin, screen.png}
방법: BAT 기하(폭/높이/base)와 색 비트순서 후보를 바꿔가며 BG 를 렌더링하고,
      스크린샷과 겹치는 위치를 찾아 일치율을 잰다. 최고 일치 조합이 정답이다.
      스프라이트(초상화·캐릭터)는 BG 에 없으므로 100% 는 나오지 않는다.
"""
import io, os, sys
import numpy as np
from PIL import Image

GT = os.path.join('translation', 'z11_probe', 'gt')
vram = np.frombuffer(open(os.path.join(GT, 'vram.bin'), 'rb').read(), dtype=np.uint8)
pal  = np.frombuffer(open(os.path.join(GT, 'palette.bin'), 'rb').read(), dtype=np.uint8)
shot = np.asarray(Image.open(os.path.join(GT, 'screen.png')).convert('RGB'))
SH, SW = shot.shape[0], shot.shape[1]
print('스크린샷 %dx%d  VRAM %d  팔레트 %d' % (SW, SH, len(vram), len(pal)))

# ---------- 타일 디코드: 8x8 4bpp 플래너, 타일당 32바이트 ----------
NT = len(vram) // 32
t = vram[:NT*32].reshape(NT, 32)
p0 = t[:,  0:16:2]; p1 = t[:,  1:16:2]          # (NT, 8)
p2 = t[:, 16:32:2]; p3 = t[:, 17:32:2]
bits = np.arange(7, -1, -1, dtype=np.uint8)      # x=0 이 최상위 비트
def plane(p):                                    # (NT,8) -> (NT,8,8)
    return ((p[:, :, None] >> bits[None, None, :]) & 1).astype(np.uint8)
TILES = plane(p0) | (plane(p1) << 1) | (plane(p2) << 2) | (plane(p3) << 3)
print('타일 %d개 디코드' % NT)

# ---------- 팔레트 ----------
pw = pal[0::2].astype(np.uint16) | (pal[1::2].astype(np.uint16) << 8)   # 512 엔트리
def make_rgb(order):
    v = pw.astype(np.int32)
    if order == 'GRB':                            # G=b6-8, R=b3-5, B=b0-2
        G, R, B = (v >> 6) & 7, (v >> 3) & 7, v & 7
    else:                                         # RGB: R=b6-8, G=b3-5, B=b0-2
        R, G, B = (v >> 6) & 7, (v >> 3) & 7, v & 7
    f = lambda c: (c * 255 // 7).astype(np.uint8)
    return np.stack([f(R), f(G), f(B)], axis=-1)  # (512,3)

# ---------- BG 렌더 ----------
def render(W, H, base_word, rgb):
    need = base_word + W * H
    if need * 2 > len(vram):
        return None
    idx = np.arange(W * H)
    off = (base_word + idx) * 2
    ent = vram[off].astype(np.uint16) | (vram[off + 1].astype(np.uint16) << 8)
    tile = (ent & 0x0FFF).astype(np.int32)
    palno = (ent >> 12).astype(np.int32)
    tile = np.clip(tile, 0, NT - 1)
    px = TILES[tile]                              # (W*H, 8, 8) 색인
    ci = palno[:, None, None] * 16 + px           # 팔레트 엔트리 번호
    ci = np.where(px == 0, 0, ci)                 # 색인0 = 백드롭
    img = rgb[ci]                                 # (W*H, 8, 8, 3)
    img = img.reshape(H, W, 8, 8, 3).transpose(0, 2, 1, 3, 4).reshape(H*8, W*8, 3)
    return img

def best_offset(img, coarse=8):
    """스크린샷과 가장 잘 겹치는 위치와 일치율.
    ★ 화면이 BAT 가장자리를 넘어 감기므로(wrap) 2x2 로 타일링한 뒤 찾는다."""
    H0, W0 = img.shape[0], img.shape[1]
    img = np.tile(img, (2, 2, 1))
    IH, IW = img.shape[0], img.shape[1]
    if IH < SH or IW < SW:
        return None
    best = (-1.0, 0, 0)
    ys = range(0, min(H0, IH - SH + 1), coarse)
    xs = range(0, min(W0, IW - SW + 1), coarse)
    s = shot[::4, ::4]
    for dy in ys:
        for dx in xs:
            sub = img[dy:dy+SH:4, dx:dx+SW:4]
            r = float((sub == s).all(axis=-1).mean())
            if r > best[0]:
                best = (r, dx, dy)
    # 정밀 보정
    r0, bx, by = best
    for dy in range(max(0, by-8), min(IH-SH, by+8)+1):
        for dx in range(max(0, bx-8), min(IW-SW, bx+8)+1):
            sub = img[dy:dy+SH:2, dx:dx+SW:2]
            r = float((sub == shot[::2, ::2]).all(axis=-1).mean())
            if r > r0:
                r0, bx, by = r, dx, dy
    return (r0, bx, by)

results = []
for order in ('GRB', 'RGB'):
    rgb = make_rgb(order)
    for (W, H) in ((64, 32), (128, 32), (32, 64), (64, 64), (128, 64), (32, 32)):
        for base in (0, W*H, 0x400, 0x800, 0x1000):
            img = render(W, H, base, rgb)
            if img is None:
                continue
            bo = best_offset(img)
            if bo is None:
                continue
            r, dx, dy = bo
            results.append((r, order, W, H, base, dx, dy))

results.sort(reverse=True)
print('\n=== 상위 후보 (일치율 순) ===')
print('%-7s %-5s %-9s %-8s %s' % ('일치율', '색순', 'BAT크기', 'base(워드)', '오프셋'))
for r, order, W, H, base, dx, dy in results[:12]:
    print('%6.1f%%  %-4s  %3dx%-3d   $%04X     (%d,%d)' % (r*100, order, W, H, base, dx, dy))

if results:
    r, order, W, H, base, dx, dy = results[0]
    rgb = make_rgb(order)
    img = render(W, H, base, rgb)
    Image.fromarray(img).save(os.path.join(GT, 'recon_full.png'))
    timg = np.tile(img, (2, 2, 1))
    Image.fromarray(timg[dy:dy+SH, dx:dx+SW]).save(os.path.join(GT, 'recon_best.png'))
    print('\n최고 후보 재현 이미지 -> gt/recon_best.png (전체 = recon_full.png)')
    print('셀->화면 변환식:  x = col*8 - %d,  y = row*8 - %d   (BAT %dx%d, base $%04X)'
          % (dx, dy, W, H, base))
