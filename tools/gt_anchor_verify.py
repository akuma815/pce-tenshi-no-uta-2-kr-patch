# -*- coding: utf-8 -*-
"""Z11 창 앵커 자기보정 — **비순환** 검증

절차 (원점을 일절 쓰지 않는다):
  A) 스크린샷에서 대사창의 화면 rect 를 독립적으로 측정 (연결성분)
  B) BAT 에서 창 채움 타일의 영역을 찾아 BAT rect 를 측정
  C) 원점 = BAT픽셀 - 화면픽셀
  D) 지상검증 정답 (352, 82) 과 일치하는지 확인
"""
import os
from collections import deque, Counter
import numpy as np
from PIL import Image

GT = os.path.join('translation', 'z11_probe', 'gt')
vram = np.frombuffer(open(os.path.join(GT, 'vram.bin'), 'rb').read(), dtype=np.uint8)
shot = np.asarray(Image.open(os.path.join(GT, 'screen.png')).convert('RGB'))
W, H = 64, 32
TRUTH = (352, 82)

# ---------- A) 스크린샷에서 대사창 rect ----------
im = Image.open(os.path.join(GT, 'screen.png')).convert('RGB')
SW, SH = im.size
px = im.load()
seen = bytearray(SW * SH)
best = None
for sy in range(SH):
    for sx in range(SW):
        if seen[sy*SW + sx]:
            continue
        c = px[sx, sy]
        q = deque([(sx, sy)]); seen[sy*SW+sx] = 1
        cells = 0; x0=x1=sx; y0=y1=sy
        while q:
            x, y = q.popleft(); cells += 1
            if x < x0: x0 = x
            if x > x1: x1 = x
            if y < y0: y0 = y
            if y > y1: y1 = y
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx, ny = x+dx, y+dy
                if 0 <= nx < SW and 0 <= ny < SH and not seen[ny*SW+nx] and px[nx,ny] == c:
                    seen[ny*SW+nx] = 1; q.append((nx, ny))
        w, h = x1-x0+1, y1-y0+1
        if cells > 3000 and w > 200 and 30 < h < 90 and cells/(w*h) > 0.75:
            if best is None or cells > best[0]:
                best = (cells, c, x0, y0, x1, y1)
print('A) 스크린샷 대사창: 색#%02X%02X%02X  rect=(%d,%d)-(%d,%d)  %dx%d'
      % (best[1][0], best[1][1], best[1][2], best[2], best[3], best[4], best[5],
         best[4]-best[2]+1, best[5]-best[3]+1))
win_sx, win_sy = best[2], best[3]

# ---------- B) BAT 에서 창 채움 타일 영역 ----------
n = W * H
ent = vram[0:n*2:2].astype(np.uint16) | (vram[1:n*2:2].astype(np.uint16) << 8)
ent = ent.reshape(H, W)
tile  = ent & 0x0FFF
palno = ent >> 12

# 창 내부는 단일 플랫 타일이 넓게 깔린다. 후보 = 셀 수가 많은 (타일,팔) 중
# 랩을 고려한 bbox 가 창 크기(약 40x6 셀)에 가까운 것.
cnt = Counter(zip(tile.ravel().tolist(), palno.ravel().tolist()))
win_w_cells = (best[4]-best[2]+1 + 7)//8
win_h_cells = (best[5]-best[3]+1 + 7)//8
print('   → 창 크기 ≈ %d x %d 셀' % (win_w_cells, win_h_cells))

def wrap_bbox(coords, size):
    """랩을 고려해 가장 좁게 감싸는 [start, length] 를 찾는다."""
    s = sorted(set(coords))
    if not s: return None
    bestlen, beststart = 10**9, s[0]
    for i in range(len(s)):
        start = s[i]
        length = max((v - start) % size for v in s) + 1
        if length < bestlen:
            bestlen, beststart = length, start
    return beststart, bestlen

print('\nB) BAT 창 채움 타일 후보')
results = []
for (t, p), c in cnt.most_common(20):
    if c < 30:
        continue
    ys, xs = np.where((tile == t) & (palno == p))
    cs, cl = wrap_bbox(xs.tolist(), W)
    rs, rl = wrap_bbox(ys.tolist(), H)
    fill = c / (cl * rl) if cl and rl else 0
    ok = abs(cl - win_w_cells) <= 6 and abs(rl - win_h_cells) <= 3
    print('   ($%03X,%2d) 셀%-4d  칼럼 %2d부터%2d개  행 %2d부터%2d개  채움%.2f%s'
          % (t, p, c, cs, cl, rs, rl, fill, '   <== 창 후보' if ok else ''))
    if ok:
        results.append((c, t, p, cs, rs, cl, rl))

# ---------- C/D) 원점 역산 + 정답 대조 ----------
print('\nC) 원점 역산 = 창의 BAT픽셀 - 창의 화면픽셀   (화면 rect = (%d,%d))' % (win_sx, win_sy))
if not results:
    print('   창 후보 없음 — 알고리즘 보완 필요')
else:
    for c, t, p, cs, rs, cl, rl in sorted(results, reverse=True):
        gx = (cs * 8 - win_sx) % (W * 8)
        gy = (rs * 8 - win_sy) % (H * 8)
        d = (TRUTH[0] - gx, TRUTH[1] - gy)
        print('   ($%03X,%d) BAT(col%d,row%d) -> 원점 (%d, %d)   정답(%d,%d) 차이 (%d,%d) %s'
              % (t, p, cs, rs, gx, gy, TRUTH[0], TRUTH[1], d[0], d[1],
                 'OK' if d == (0, 0) else ''))
