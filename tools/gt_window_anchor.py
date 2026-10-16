# -*- coding: utf-8 -*-
"""Z11 창 앵커 자기보정 — 알고리즘 검증 (오프라인)

목적: BAT 에서 대사창 블록을 찾아 BAT 좌표를 얻고,
      원점 = 창의 BAT픽셀 - 창의 화면픽셀  로 역산되는지 확인한다.
정답(지상검증 §4e): 원점 = (352, 82), BAT 64x32, base $0000.
"""
import os
import numpy as np
from collections import Counter

GT = os.path.join('translation', 'z11_probe', 'gt')
vram = np.frombuffer(open(os.path.join(GT, 'vram.bin'), 'rb').read(), dtype=np.uint8)
W, H = 64, 32
OX, OY = 352, 82                      # 지상검증 정답 원점

n = W * H
ent = vram[0:n*2:2].astype(np.uint16) | (vram[1:n*2:2].astype(np.uint16) << 8)
ent = ent.reshape(H, W)
tile  = (ent & 0x0FFF)
palno = (ent >> 12)

def to_screen(col, row):
    return ((col * 8 - OX) % (W * 8), (row * 8 - OY) % (H * 8))

# ---------- 1. 정답 원점으로 "화면에 보이는" BAT 영역을 확인 ----------
print('=== 정답 원점 기준: 화면(0,0)-(351,233) 에 해당하는 BAT 셀 ===')
c0 = (OX // 8) % W                      # 화면 x=0 에 해당하는 칼럼
r0 = (OY // 8) % H
print('화면 좌상단 ≈ BAT (col %d, row %d),  서브타일 오프셋 (%d, %d)'
      % (c0, r0, OX % 8, OY % 8))

# ---------- 2. 대사창이 있어야 할 화면 y=166..206 구간의 BAT 행 ----------
print('\n=== 화면 y=160..210 구간의 BAT 행별 타일 구성 ===')
for sy in range(160, 212, 8):
    row = ((sy + OY) // 8) % H
    # 화면 x=0..351 -> 칼럼
    cols = [((sx + OX) // 8) % W for sx in range(0, 352, 8)]
    ts = [int(tile[row, c]) for c in cols]
    cc = Counter(ts)
    top = cc.most_common(2)
    print('  화면y=%3d  BAT행%2d | 최다타일 $%03X x%2d, $%03X x%2d | 고유 %d종'
          % (sy, row, top[0][0], top[0][1],
             (top[1][0] if len(top) > 1 else 0), (top[1][1] if len(top) > 1 else 0),
             len(cc)))

# ---------- 3. 최대 동일-타일 직사각형 (히스토그램 법) ----------
def max_rect(mask):
    """all-true 최대 직사각형 -> (x0,y0,x1,y1,area)"""
    Hh, Ww = mask.shape
    heights = np.zeros(Ww, dtype=int)
    best = (0, None)
    for y in range(Hh):
        heights = np.where(mask[y], heights + 1, 0)
        stack = []
        for x in range(Ww + 1):
            h = heights[x] if x < Ww else 0
            start = x
            while stack and stack[-1][1] >= h:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, (sx, y - sh + 1, x - 1, y))
                start = sx
            stack.append((start, h))
    return best

T2 = np.tile(tile, (2, 2))
P2 = np.tile(palno, (2, 2))
cnt = Counter(zip(tile.ravel().tolist(), palno.ravel().tolist()))

print('\n=== 동일-타일 최대 직사각형 (셀 20개 이상인 타일만) ===')
print('%-11s %-5s %-20s %-7s %s' % ('(타일,팔)', '총셀', 'BAT rect', '크기', '화면 좌상단'))
cands = []
for (t, p), c in cnt.most_common(30):
    if c < 20:
        continue
    area, r = max_rect((T2 == t) & (P2 == p))
    if not r or area < 20:
        continue
    x0, y0, x1, y1 = r
    if x0 >= W or y0 >= H:              # 2x2 확장본의 좌상단 사분면에서 시작하는 것만
        continue
    cands.append((area, t, p, x0, y0, x1, y1))

cands.sort(reverse=True)
for area, t, p, x0, y0, x1, y1 in cands[:10]:
    sx, sy = to_screen(x0, y0)
    print('($%03X,%2d)   %-4d  (%2d,%2d)-(%2d,%2d)  %2dx%-2d   화면(%3d,%3d)%s'
          % (t, p, cnt[(t, p)], x0, y0, x1, y1, x1-x0+1, y1-y0+1, sx, sy,
             '   <== 대사창 위치' if 150 <= sy <= 215 else ''))

# ---------- 4. 역산 검증 ----------
print('\n=== 역산 검증: 창 블록 -> 원점 ===')
for area, t, p, x0, y0, x1, y1 in cands[:10]:
    sx, sy = to_screen(x0, y0)
    if 150 <= sy <= 215:
        gx = (x0 * 8 - sx) % (W * 8)
        gy = (y0 * 8 - sy) % (H * 8)
        print('  블록($%03X,%d) BAT(%d,%d) + 화면(%d,%d) -> 원점 (%d, %d)  %s'
              % (t, p, x0, y0, sx, sy, gx, gy,
                 'OK' if (gx, gy) == (OX, OY) else '(서브타일 오차 %d,%d)' % (OX-gx, OY-gy)))
