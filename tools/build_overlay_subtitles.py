# -*- coding: utf-8 -*-
"""Z11 번역표 생성기 — 수확 버스트 키 -> 세그먼트별 한글

입력:
  translation/z11_probe/harvest/harvest.tsv   실플레이 수확 버스트(원문 SJIS)
  translation/script_sheet.tsv                원문 -> 번역 코퍼스
출력:
  translation/z11_probe/overlay_subtitles.csv  sjis_hex \t source \t text_ko

원리: 버스트는 창 하나에 그려진 문자 전체다. 코퍼스 레코드 여러 개가 이어붙은
      형태이므로, 코퍼스 원문으로 **탐욕적 분할**해 세그먼트를 만든다.
      세그먼트 순서 = 렌더 순서 = 오버레이의 '|' 순서.
"""
import io, os, re, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARVEST = os.path.join('translation', 'z11_probe', 'harvest', 'harvest.tsv')
SHEET   = os.path.join('translation', 'script_sheet.tsv')
OUT     = os.path.join('translation', 'z11_probe', 'overlay_subtitles.csv')
UNMATCHED = os.path.join('translation', 'z11_probe', 'overlay_unmatched.tsv')

CTRL = re.compile(r'\{[^}]*\}')                   # {0B}, {~}, {%s}, {#5} 등 제어/자리표시자
FMT  = re.compile(r'#\d')                        # 코퍼스의 서식 마커 (#1, #5 …)
BRK  = re.compile(r'\\[np]')                     # 줄바꿈/페이지 마커 — 파일에 리터럴 2글자로 들어있다

def clean(s):
    """렌더되지 않는 제어 토큰을 제거해 버스트 키와 비교 가능한 형태로."""
    return FMT.sub('', CTRL.sub('', s)).strip()

def lines_of(s):
    """코퍼스 텍스트를 줄 단위로 쪼갠다.
    ★ 줄바꿈 마커(\\n, \\p)는 렌더되지 않으므로 버스트 키에는 없다.
      동시에 이것이 오버레이가 필요로 하는 세그먼트 경계이기도 하다."""
    return [x for x in (clean(p) for p in BRK.split(s)) if x]

PAGE = re.compile(r'\\p')                        # 페이지 구분 — 창은 한 번에 한 페이지만 보여준다

def pages_of(s):
    """레코드를 페이지 단위로, 각 페이지를 줄 단위로 쪼갠다."""
    return [lines_of(pg) for pg in PAGE.split(s)]

# ---------- 코퍼스 ----------
pairs = {}
patterns = []          # 자리표시자 레코드: (컴파일된 정규식, 한글 템플릿 줄들)
n_sheet = 0

TOKEN = re.compile(r'\{%[sd]\}')

def make_pattern(jp_raw, ko_raw, trusted=False):
    """{%s}/{%d} 를 **제거하지 말고 와일드카드로** 바꿔 패턴을 만든다.
    제거하면 원문이 이어붙어 매칭 불가능한 문자열이 된다(초기 실패 원인)."""
    for jpg, kpg in zip(PAGE.split(jp_raw), PAGE.split(ko_raw)):
        # 페이지 단위: 줄바꿈을 없앤 형태가 버스트와 같은 모양
        j = FMT.sub('', BRK.sub('', jpg))
        # ★ 한글 템플릿의 자리표시자는 `{%s}` 형태로 들어있다(Z8 색인 4,210행 전부).
        #   clean() 은 `{...}` 를 통째로 지우므로 그대로 넘기면 채울 자리가 사라지고,
        #   결과가 원문보다 너무 짧아져 품질 게이트에서 전량 폐기된다(실측 원인).
        #   지우기 전에 `%s`/`%d` 로 바꿔 fill() 이 쓸 수 있게 남긴다.
        kpg = TOKEN.sub(lambda m: m.group(0)[1:-1], kpg)
        k_lines = [x for x in (clean(p) for p in BRK.split(kpg)) if x]
        if '{%' not in j or not k_lines:
            continue
        parts, last, groups, lits = [], 0, [], []
        for m in TOKEN.finditer(j):
            lit = CTRL.sub('', j[last:m.start()])
            parts.append(re.escape(lit)); lits.append(lit)
            groups.append(m.group(0))
            parts.append(r'([0-9０-９]+)' if m.group(0) == '{%d}' else r'(.{1,12}?)')
            last = m.end()
        lit = CTRL.sub('', j[last:])
        parts.append(re.escape(lit)); lits.append(lit)
        pat = ''.join(parts)
        if len(pat) < 8:            # 너무 헐거운 패턴은 오매칭을 부른다
            continue
        # ★ 선필터용 리터럴 앵커는 **정규식 문자열에서 역추적하지 않고** 여기서 직접 기록한다.
        #   정규식에서 다시 도려내면 `[0-9０-９]` 같은 문자클래스 내부가
        #   앵커로 잡혀 본문에 없는 문자열이 되고, 해당 패턴이 전량 배제된다(실측).
        hint = max(lits, key=len)
        try:
            patterns.append((re.compile(pat), k_lines, groups, hint, trusted))
        except re.error:
            pass

def index_record(jp, ko, trusted=False):
    """레코드를 세 단위로 색인한다.
      · 레코드 전체 · 페이지별 · 줄별
    버스트는 창 하나에 그려진 문자 전체 = 보통 '한 페이지'이므로 페이지 단위가 핵심이고,
    줄 단위 색인은 접두 잡음(추출 아티팩트)이 있어도 이어붙여 복원할 수 있게 해준다."""
    if '{%' in jp:
        make_pattern(jp, ko, trusted)  # 자리표시자 레코드는 패턴으로도 등록
    jpg, kpg = pages_of(jp), pages_of(ko)
    # 레코드 전체
    aj = [x for pg in jpg for x in pg]
    ak = [x for pg in kpg for x in pg]
    if aj and ak:
        pairs.setdefault(''.join(aj), ak)
    # 페이지별 (JP/KO 페이지 수가 같을 때만 신뢰)
    if len(jpg) == len(kpg):
        for j, k in zip(jpg, kpg):
            if j and k:
                pairs.setdefault(''.join(j), k)
            # 줄별 (줄 수가 같을 때만 1:1 대응)
            if len(j) == len(k):
                for jl, kl in zip(j, k):
                    # ★ 1글자 항목은 색인하지 않는다.
                    #   Z8 색인에 섞인 1글자 잡음(예: 'あ'->'아')이 탐욕 분할기에서
                    #   텍스트를 잘게 부숴 출력이 깨진다(실측: 레벨업 메시지 파손).
                    if len(jl) >= 2 and kl.strip():
                        pairs.setdefault(jl, [kl])
# ---------- 보충 코퍼스: Z11 오버레이 전용 런타임 조립 문자열 ----------
# 엔진이 라벨·이름·수치를 런타임에 이어붙이는 문장은 어느 코퍼스에도 원문이 없다.
# 손으로 쓴 신뢰 코퍼스이므로 **가장 먼저** 읽어 setdefault 우선권을 준다.
SUPP = os.path.join('translation', 'z11_overlay_supplement.tsv')
n_supp = 0
if os.path.exists(SUPP):
    with io.open(SUPP, encoding='utf-8-sig') as f:
        f.readline()
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            p3 = line.rstrip('\n').split('\t')
            if len(p3) >= 2 and p3[0].strip() and p3[1].strip():
                index_record(p3[0].strip(), p3[1].strip(), trusted=True); n_supp += 1

with io.open(SHEET, encoding='utf-8-sig') as f:
    f.readline()
    for line in f:
        p = line.rstrip('\n').split('\t')
        if len(p) < 5:
            continue
        jp, ko = p[3], p[4]
        n_sheet += 1
        if ko.strip():
            index_record(jp, ko)
# ---------- 추가 코퍼스: 메뉴 오버라이드 (orig 행) ----------
MENU = os.path.join('translation', 'b10_menu_overrides.tsv')
n_menu = 0
if os.path.exists(MENU):
    with io.open(MENU, encoding='utf-8-sig') as f:
        f.readline()
        for line in f:
            p3 = line.rstrip('\n').split('\t')
            if len(p3) >= 3 and p3[0] == 'orig' and p3[1].strip() and p3[2].strip():
                j = ''.join(lines_of(p3[1]))
                if j:
                    pairs.setdefault(j, lines_of(p3[2])); n_menu += 1

# ---------- 추가 코퍼스: 미인덱스 전투 메시지 (old_hex 디코드) ----------
BATT = os.path.join('translation', 'b10_unindexed_battle.tsv')
n_batt = 0
def dec_hex(h):
    try:
        b = bytes.fromhex(h)
    except Exception:
        return ''
    b = bytes(c for c in b if c >= 0x20)          # 제어바이트 제거
    try:
        return b.decode('shift_jis', 'ignore')
    except Exception:
        return ''
if os.path.exists(BATT):
    with io.open(BATT, encoding='utf-8-sig') as f:
        f.readline()
        for line in f:
            p3 = line.rstrip('\n').split('\t')
            if len(p3) >= 2 and p3[0].strip() and p3[1].strip():
                j = ''.join(lines_of(dec_hex(p3[0].strip())))
                if j:
                    pairs.setdefault(j, lines_of(p3[1])); n_batt += 1

# ---------- 추가 코퍼스: NOFIT 워크리스트 (original/translation) ----------
WORK = os.path.join('translation', 'btrack_b10_menu_worklist.tsv')
n_work = 0
if os.path.exists(WORK):
    with io.open(WORK, encoding='utf-8-sig') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        try:
            oi, ti = hdr.index('original'), hdr.index('translation')
        except ValueError:
            oi = ti = None
        if oi is not None:
            for line in f:
                p3 = line.rstrip('\n').split('\t')
                if len(p3) > max(oi, ti) and p3[oi].strip() and p3[ti].strip():
                    j = ''.join(lines_of(p3[oi]))
                    if j:
                        pairs.setdefault(j, lines_of(p3[ti])); n_work += 1

# ---------- 추가 코퍼스: Z8 텍스트 엔트리 색인 (original/translation, 18,817행) ----------
# 이름류(무기·방어구·몬스터·아이템·지명)가 여기에만 있다.
IDX = os.path.join('translation', 'ziria_z8_text_entry_index.csv')
n_idx = 0
if os.path.exists(IDX):
    import csv as _csv
    with io.open(IDX, encoding='utf-8-sig', newline='') as f:
        for r in _csv.DictReader(f):
            o = (r.get('original') or '').strip()
            t = (r.get('translation') or '').strip()
            if o and t and o != t:
                index_record(o, t); n_idx += 1

# ---------- 추가 코퍼스: b9 누락 보충 (jp/ko) ----------
GAP = os.path.join('translation', 'b9_gap_supplement_source.tsv')
n_gap = 0
if os.path.exists(GAP):
    with io.open(GAP, encoding='utf-8-sig') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        try:
            ji, ki = hdr.index('jp'), hdr.index('ko')
        except ValueError:
            ji = ki = None
        if ji is not None:
            for line in f:
                p3 = line.rstrip('\n').split('\t')
                if len(p3) > max(ji, ki) and p3[ji].strip() and p3[ki].strip():
                    index_record(p3[ji], p3[ki]); n_gap += 1

print('코퍼스: 오버레이보충 %d + script_sheet %d + 메뉴 %d + 전투 %d + 워크리스트 %d + Z8색인 %d + 보충 %d'
      % (n_supp, n_sheet, n_menu, n_batt, n_work, n_idx, n_gap))
print('  -> 매칭 가능 원문 %d종' % len(pairs))

# 길이 내림차순 (탐욕 분할에서 긴 것 우선)
keys_by_len = sorted(pairs.keys(), key=len, reverse=True)
by_first = {}
for k in keys_by_len:
    by_first.setdefault(k[0], []).append(k)

PAT = list(patterns)          # (정규식, 한글 템플릿 줄들, 그룹종류, 리터럴 앵커, 신뢰여부)
print('  자리표시자 패턴 %d종' % len(PAT))

# 마지막 글자의 받침 유무 (없으면 None = 판정 불가)
_DIGIT_JONG = {'0': 8, '1': 8, '2': 0, '3': 16, '4': 0,
               '5': 0, '6': 1, '7': 8, '8': 8, '9': 0}   # 영/일/이/삼/사/오/육/칠/팔/구

def _jong(v):
    v = v.rstrip()
    if not v:
        return None
    c = v[-1]
    if '가' <= c <= '힣':
        return (ord(c) - 0xAC00) % 28
    if c.isdigit():
        return _DIGIT_JONG.get(str(int(c)) if c.isascii() else
                               '0123456789'[ord(c) - ord('０')])
    return None

# (받침 있을 때, 받침 없을 때) — 둘 중 어느 쪽이 템플릿에 적혀 있어도 인식한다
_JOSA = [('으로', '로'), ('은', '는'), ('이', '가'),
         ('을', '를'), ('과', '와')]

# 괄호 병기형 — `script_sheet.tsv` 31행이 `%s(은)는 …` 꼴이다.
# 오버레이는 **자동 선택**으로 통일한다(2026-09-01 사용자 결정)이므로
# 이것도 한쪽으로 접는다. 안 접으면 화면에 `클로우(은)는` 이 그대로 나간다.
_JOSA_PAREN = [('(%s)%s' % (a, b), (a, b)) for a, b in
               [('은', '는'), ('이', '가'), ('을', '를'), ('과', '와')]]
_JOSA_PAREN.append(('(으)로', ('으로', '로')))

def fix_josa(val, ln, i):
    """치환 직후의 조사를 채워 넣은 값의 받침에 맞춰 고른다.
    ★ 이 보정은 오버레이 트랙에서만 가능하다 — in-place 는 엔진이 런타임에
      이름을 넣으므로 조사를 고를 수 없어 아예 빼는 규칙이었다(HANDOFF §6).
      여기서는 생성 시점에 실제 이름을 알고 있으므로 '고블린는' 을 고칠 수 있다.
    반환: (조사문자열, 다음 인덱스) 또는 None."""
    j = _jong(val)
    if j is None:
        return None
    for tok, (a, b) in _JOSA_PAREN:
        if ln.startswith(tok, i):
            if (a, b) == ('으로', '로'):
                return ('으로' if j and j != 8 else '로'), i + len(tok)
            return (a if j else b), i + len(tok)
    for a, b in _JOSA:
        for tok in (a, b):
            if ln.startswith(tok, i):
                if (a, b) == ('으로', '로'):
                    # ㄹ 받침(8)은 '로' 를 쓴다
                    return ('으로' if j and j != 8 else '로'), i + len(tok)
                return (a if j else b), i + len(tok)
    return None

def fill(k_lines, caps):
    """한글 템플릿의 %s/%d 를 캡처값으로 채운다. 캡처는 가능하면 번역한다."""
    vals = []
    for c in caps:
        t = pairs.get(c)
        vals.append(t[0] if t else c)
    out, vi = [], 0
    # ★ 캡처 인덱스는 **줄을 넘어 이어진다**. 줄마다 0으로 되돌리면 여러 줄에
    #   걸친 템플릿이 첫 캡처만 반복한다(실측: `６경험치와|６기밀을얻었다`).
    for ln in k_lines:
        r, i = '', 0
        while i < len(ln):
            if ln[i] == '%' and i + 1 < len(ln) and ln[i+1] in 'sd':
                v = vals[vi] if vi < len(vals) else ''
                r += v
                vi += 1; i += 2
                jz = fix_josa(v, ln, i) if v else None
                if jz:
                    r += jz[0]; i = jz[1]
            else:
                r += ln[i]; i += 1
        out.append(r)
    return out

def caps_ok(groups, caps):
    """★ 패턴이 이기려면 **캡처가 전부 번역 가능**해야 한다.
    `{%s}` 는 `.{1,12}?` 라 앞 문맥을 통째로 삼킬 수 있다. 그러면 패턴이 더
    길다는 이유로 정확 매칭을 이기고, 채워 넣을 번역이 없는 캡처는 일본어
    그대로 출력된다(실측: `フェイトシオン　シオン는１피해!`).
    번역 가능 = 코퍼스에 있거나, 애초에 번역이 필요 없는 숫자·기호·공백."""
    for g, c in zip(groups, caps):
        if g == '{%d}' or c in pairs:
            continue
        if not any(ch.isalpha() for ch in c):
            continue
        return False
    return True

def best_pattern(rest, pats):
    """rest 의 시작점에서 매칭되는 자리표시자 패턴 중 **가장 긴 것**을 고른다.
    첫 성공에서 멈추면 짧은 패턴이 긴 패턴을 가로챈다."""
    best = None
    for rx, k_lines, groups, hint, trusted in pats:
        if hint not in rest:
            continue
        m = rx.match(rest)
        if not m or m.end() < 6:
            continue
        if best is not None and m.end() <= best[0].end():
            continue
        if not caps_ok(groups, m.groups()):
            continue
        out = fill(k_lines, list(m.groups()))
        # 품질 게이트: 빈 줄이 생기거나 원문 대비 과도하게 짧으면 버린다.
        if any(not x.strip() for x in out):
            continue
        if sum(len(x) for x in out) * 3 < m.end():
            continue
        best = (m, out)
    return best

def split_greedy(text):
    """text 를 코퍼스 원문들로 왼쪽부터 탐욕 분할. (세그먼트리스트, 미매칭문자수)"""
    # 이 버스트에 리터럴 앵커가 등장하는 패턴만 추린다.
    # 품질 게이트 ①: 앵커 4자 이상 — 짧은 앵커 + 헐거운 와일드카드는 엉뚱한 곳에
    # 걸려 출력이 깨진다(실측). 위치마다 7,956종을 다 도는 것도 막는다.
    # 신뢰 패턴(손으로 쓴 보충 코퍼스)은 앵커 길이 게이트를 면제한다.
    pats = [p for p in PAT if (p[4] or len(p[3]) >= 4) and p[3] in text]
    segs, i, miss = [], 0, 0
    while i < len(text):
        hit = None
        for cand in by_first.get(text[i], ()):
            if text.startswith(cand, i):
                hit = cand
                break
        pm = best_pattern(text[i:], pats)
        # ★ 정확 매칭보다 패턴이 길면 패턴을 택한다.
        #   탐욕 분할이 이름(`クロウラー`)만 집어먹고 남은 `は８のダメージ！`를
        #   버리는 것이 미번역 세그먼트의 최대 원인이었다(실측 30종 중 20종).
        if pm is not None and (hit is None or pm[0].end() > len(hit)):
            m, out = pm
            segs.append((m.group(0), out))
            i += m.end()
            continue
        if hit:
            segs.append((hit, pairs[hit]))
            i += len(hit)
            continue
        # 미매칭 1글자 흘려보냄
        if segs and segs[-1][1] is None:
            segs[-1] = (segs[-1][0] + text[i], None)
        else:
            segs.append((text[i], None))
        i += 1
        if text[i-1].strip():        # 공백은 번역 대상이 아니다 — 미매칭으로 세지 않는다
            miss += 1
    return segs, miss

# ---------- 수확 버스트 ----------
def dec(h):
    out = []
    for i in range(0, len(h), 4):
        try:
            out.append(bytes.fromhex(h[i:i+4]).decode('shift_jis'))
        except Exception:
            out.append('�')
    return ''.join(out)

rows = [l.rstrip('\n').split('\t') for l in io.open(HARVEST, encoding='utf-8')][1:]
rows = [r for r in rows if len(r) >= 4 and r[3]]
seen_keys = {}
for r in rows:
    seen_keys.setdefault(r[3], dec(r[3]))
print('수확 고유 버스트 %d종 (총 %d이벤트)' % (len(seen_keys), len(rows)))

full, partial, none_, n_blank = 0, 0, 0, 0
out_rows = []
unmatched = []                          # (버스트키, 미매칭 세그먼트 원문, 버스트 전문)
for key, jp in seen_keys.items():
    segs, miss = split_greedy(jp)
    ko_parts, holes, blank = [], [], 0
    for sj, ko in segs:
        if ko:
            ko_parts.extend(ko)        # 코퍼스 줄 = 오버레이 세그먼트
        else:
            ko_parts.append('')
            # 공백만 있는 런은 번역할 것이 없다(파티창 여백 등). 덮지도, 세지도 않는다.
            if sj.strip():
                holes.append((key, sj, jp))
            else:
                blank += 1
    if miss == 0 and any(ko_parts):
        full += 1
    elif any(ko_parts):
        partial += 1
    else:
        none_ += 1
        continue
    unmatched.extend(holes)
    n_blank += blank
    out_rows.append((key, jp, '|'.join(ko_parts), miss, len(segs)))

print('\n=== 매칭 결과 ===')
print('  완전 매칭 : %d' % full)
print('  부분 매칭 : %d' % partial)
print('  매칭 실패 : %d' % none_)
print('  -> 생성 대상 %d종' % len(out_rows))

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('sjis_hex\tsource\ttext_ko\tmiss\tsegs\n')
    for key, jp, ko, miss, ns in sorted(out_rows, key=lambda r: -len(r[1])):
        f.write('%s\t%s\t%s\t%d\t%d\n' % (key, jp, ko, miss, ns))
print('\n출력: %s' % OUT)

# ---------- 세그먼트 커버리지 + 미번역 진단 ----------
# 릴리스 판정 지표는 버스트가 아니라 **세그먼트**다 (Z11 §4g).
seg_tot = sum(len(r[2].split('|')) for r in out_rows)
seg_emp = len(unmatched)
print('\n=== 세그먼트 커버리지 ===')
print('  전체 %d / 미번역 %d -> %.1f%%'
      % (seg_tot, seg_emp, 100.0 * (seg_tot - seg_emp) / max(seg_tot, 1)))

with io.open(UNMATCHED, 'w', encoding='utf-8') as f:
    f.write('count\tjp_segment\tburst_sample\n')
    agg = {}
    for key, sj, jp in unmatched:
        a = agg.setdefault(sj, [0, jp])
        a[0] += 1
    for sj, (n, jp) in sorted(agg.items(), key=lambda kv: (-kv[1][0], -len(kv[0]))):
        f.write('%d\t%s\t%s\n' % (n, sj, jp))
print('미번역 진단: %s (%d종)' % (UNMATCHED, len(agg)))

print('\n=== 표본 (완전 매칭 상위 5) ===')
shown = 0
for key, jp, ko, miss, ns in sorted(out_rows, key=lambda r: (r[3], -len(r[1]))):
    if miss == 0 and shown < 5:
        print('  원문(%2d자): %s' % (len(jp), jp[:48]))
        print('  한글(%2d세그): %s' % (ns, ko[:70]))
        shown += 1
