# -*- coding: utf-8 -*-
"""Z11 창 보정기 — 스크린샷에서 텍스트 창의 색·rect·글자 원점을 자동 추출한다.

사용: python -X utf8 tools/build_overlay_rects.py <png...>
출력: translation/z11_probe/overlay_rects_detected.tsv  (사람이 class 열만 채우면 됨)

원리: 게임 창은 단일 플랫 색 직사각형이다. 연결 성분 중 채움률이 높고 면적이
큰 것이 창이며, 창 안에서 배경색이 아닌 픽셀의 바운딩 박스가 글자 영역이다.
"""
import sys, io, os
from collections import deque, Counter
from PIL import Image

MIN_AREA   = 600     # 창 후보 최소 픽셀
MIN_FILL   = 0.80    # 직사각형 채움률 (글자가 구멍을 내므로 1.0 미만)
MIN_W, MIN_H = 40, 20

def components(im):
    W, H = im.size; px = im.load()
    seen = bytearray(W * H)
    out = []
    for sy in range(H):
        for sx in range(W):
            if seen[sy * W + sx]: continue
            c = px[sx, sy]; q = deque([(sx, sy)]); seen[sy * W + sx] = 1
            cnt = 0; x0 = x1 = sx; y0 = y1 = sy
            while q:
                x, y = q.popleft(); cnt += 1
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny*W+nx] and px[nx,ny] == c:
                        seen[ny*W+nx] = 1; q.append((nx, ny))
            if cnt >= MIN_AREA:
                w, h = x1-x0+1, y1-y0+1
                out.append((cnt, c, x0, y0, x1, y1, cnt/(w*h)))
    return out

INSET = 3            # 테두리·모서리를 제외하기 위한 인셋

def text_extent(im, bg, x0, y0, x1, y1):
    """창 내부(테두리 인셋 후)에서 배경색이 아닌 픽셀(=글자)의 바운딩 박스."""
    px = im.load()
    x0, y0, x1, y1 = x0+INSET, y0+INSET, x1-INSET, y1-INSET
    if x1 <= x0 or y1 <= y0: return None
    tx0 = ty0 = 10**9; tx1 = ty1 = -1
    for y in range(y0, y1+1):
        for x in range(x0, x1+1):
            if px[x, y] != bg:
                if x < tx0: tx0 = x
                if x > tx1: tx1 = x
                if y < ty0: ty0 = y
                if y > ty1: ty1 = y
    if tx1 < 0: return None
    return tx0, ty0, tx1, ty1

def main(paths):
    rows = []
    for p in paths:
        im = Image.open(p).convert('RGB'); W, H = im.size
        for cnt, c, x0, y0, x1, y1, fill in components(im):
            w, h = x1-x0+1, y1-y0+1
            if fill < MIN_FILL or w < MIN_W or h < MIN_H: continue
            if w >= W - 2 and h >= H - 2: continue          # 화면 전체
            if y0 >= H - 14: continue                        # 하단 레터박스
            te = text_extent(im, c, x0, y0, x1, y1)
            rows.append(dict(
                src=os.path.basename(p), sw=W, sh=H,
                color='#%02X%02X%02X' % c,
                x=x0, y=y0, w=w, h=h, fill=round(fill, 3),
                tx=te[0] if te else '', ty=te[1] if te else '',
                tw=(te[2]-te[0]+1) if te else '', th=(te[3]-te[1]+1) if te else '',
                pad_l=(te[0]-x0) if te else '', pad_t=(te[1]-y0) if te else ''))
    rows.sort(key=lambda r: (r['src'], -r['w']*r['h']))
    out = 'translation/z11_probe/overlay_rects_detected.tsv'
    cols = ['class','src','sw','sh','color','x','y','w','h','fill','tx','ty','tw','th','pad_l','pad_t']
    with io.open(out, 'w', encoding='utf-8') as f:
        f.write('\t'.join(cols) + '\n')
        for r in rows:
            r['class'] = ''
            f.write('\t'.join(str(r[c]) for c in cols) + '\n')
    print('창 후보 %d건 -> %s' % (len(rows), out))
    for r in rows:
        print('  %-18s %s  rect=(%3d,%3d) %3dx%-3d  글자=(%s,%s) %sx%s  여백 L%s T%s' % (
            r['src'], r['color'], r['x'], r['y'], r['w'], r['h'],
            r['tx'], r['ty'], r['tw'], r['th'], r['pad_l'], r['pad_t']))

def expand(args):
    """디렉터리를 받으면 그 안의 png 전량으로 편다.
    ★ 셸 글롭(`harvest/*.png`)은 수확이 커지면 **인자 길이 초과로 실행조차 안 된다**
      (1,130장에서 실측). 디렉터리를 넘기는 쪽을 기본 사용법으로 삼는다."""
    import glob
    out = []
    for a in args:
        if os.path.isdir(a):
            out.extend(sorted(glob.glob(os.path.join(a, '*.png'))))
        else:
            out.extend(sorted(glob.glob(a)) or [a])
    return out

if __name__ == '__main__':
    paths = expand(sys.argv[1:]) or ['translation/z11_probe/harvest']
    if len(paths) == 1 and os.path.isdir(paths[0]):
        paths = expand(paths)
    print('입력 %d장' % len(paths))
    main(paths)
