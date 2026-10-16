# -*- coding: utf-8 -*-
"""Z11 창 클래스 표 생성기 — 수확 rect 실측 -> 오버레이가 읽는 classes.lua

입력:  translation/z11_probe/overlay_rects_detected.tsv  (build_overlay_rects.py 산출)
출력:  translation/z11_probe/classes.lua                 (overlay_z11_final.lua 가 dofile)

원리: 같은 창은 수확 스크린샷마다 **같은 (색, x, y, w, h)** 로 검출된다.
      그걸 세어 자주 나온 것만 남기면 그것이 실사용 창 클래스다.

왜 이 단계가 도구여야 하는가: 수확을 넓힐 때마다(Z11.3) 클래스 표를 다시 만들어야
한다. 손으로 옮겨 적으면 오버레이의 표와 실측이 어긋나고, 어긋난 클래스는 원점을
통째로 틀리게 만든다. 매처 자기검증이 잘못된 후보를 걸러 주기는 하지만,
**후보 목록에 정답이 없으면 걸러 낼 것도 없다.**
"""
import io, os, sys, collections

RECTS = os.path.join('translation', 'z11_probe', 'overlay_rects_detected.tsv')
OUT   = os.path.join('translation', 'z11_probe', 'classes.lua')

MIN_HITS = 3          # 이보다 드물면 검출 잡음으로 본다 (47종 = 실사용 창)
SKIP_COLORS = {'#000000'}   # 검은 레터박스·화면 배경은 창이 아니다

def main(min_hits=MIN_HITS):
    with io.open(RECTS, encoding='utf-8') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        ix = {c: n for n, c in enumerate(hdr)}
        rows = [l.rstrip('\n').split('\t') for l in f if l.strip()]

    cnt = collections.Counter()
    for r in rows:
        color = r[ix['color']]
        if color in SKIP_COLORS:
            continue
        cnt[(color, int(r[ix['x']]), int(r[ix['y']]),
             int(r[ix['w']]), int(r[ix['h']]))] += 1

    keep = [(k, v) for k, v in cnt.items() if v >= min_hits]
    keep.sort(key=lambda kv: (-kv[1], kv[0]))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write('-- 자동 생성 — build_overlay_classes.py. 손으로 고치지 말 것.\n')
        f.write('-- 입력 %s (창 후보 %d건), hits >= %d 만 채택.\n'
                % (RECTS.replace(os.sep, '/'), len(rows), min_hits))
        f.write('-- 매처는 cw/ch 를 쓰지 않는다 — "화면크기 - 채움블록크기 = 테두리 폭"\n')
        f.write('-- 으로 판정하므로 화면 rect(sx,sy,sw,sh)만 있으면 된다.\n')
        f.write('return {\n')
        for (color, x, y, w, h), n in keep:
            f.write('  { name = "c%s_%dx%d", sx = %d, sy = %d, sw = %d, sh = %d, hits = %d },\n'
                    % (color.lstrip('#'), w, h, x, y, w, h, n))
        f.write('}\n')

    print('창 후보 %d건 -> 그룹 %d종 -> 채택 %d종 (hits >= %d)'
          % (len(rows), len(cnt), len(keep), min_hits))
    print('출력: %s' % OUT)
    for (color, x, y, w, h), n in keep[:10]:
        print('  %-9s (%3d,%3d) %3dx%-3d  hits %d' % (color, x, y, w, h, n))

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else MIN_HITS)
