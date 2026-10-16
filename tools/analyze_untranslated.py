# -*- coding: utf-8 -*-
"""Z11 — 미번역 세그먼트의 정체 분류

생성기와 같은 방식으로 버스트를 분할하되, **매칭되지 않은 일본어 조각**을 모아
성격별로 나눈다. 패턴 매칭(자리표시자 와일드카드)이 얼마나 회수할지 판단하기 위함.
"""
import io, os, re, csv
from collections import Counter

CTRL = re.compile(r'\{[^}]*\}')
FMT  = re.compile(r'#\d')
BRK  = re.compile(r'\\[np]')
PAGE = re.compile(r'\\p')

def clean(s):  return FMT.sub('', CTRL.sub('', s)).strip()
def lines_of(s): return [x for x in (clean(p) for p in BRK.split(s)) if x]
def pages_of(s): return [lines_of(pg) for pg in PAGE.split(s)]

pairs = {}
raw_originals = []          # 자리표시자를 **가진 채로** 보관 (패턴 매칭 후보)

def index_record(jp, ko):
    if '{%' in jp:
        raw_originals.append((jp, ko))
    jpg, kpg = pages_of(jp), pages_of(ko)
    aj = [x for pg in jpg for x in pg]
    ak = [x for pg in kpg for x in pg]
    if aj and ak:
        pairs.setdefault(''.join(aj), ak)
    if len(jpg) == len(kpg):
        for j, k in zip(jpg, kpg):
            if j and k:
                pairs.setdefault(''.join(j), k)
            if len(j) == len(k):
                for jl, kl in zip(j, k):
                    if jl and kl:
                        pairs.setdefault(jl, [kl])

# ---- 코퍼스 (생성기와 동일) ----
with io.open(os.path.join('translation', 'script_sheet.tsv'), encoding='utf-8-sig') as f:
    f.readline()
    for line in f:
        p = line.rstrip('\n').split('\t')
        if len(p) >= 5 and p[4].strip():
            index_record(p[3], p[4])
with io.open(os.path.join('translation', 'ziria_z8_text_entry_index.csv'), encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        o = (r.get('original') or '').strip(); t = (r.get('translation') or '').strip()
        if o and t and o != t:
            index_record(o, t)
for path, a, b in [('b10_menu_overrides.tsv', 1, 2), ('btrack_b10_menu_worklist.tsv', None, None)]:
    fp = os.path.join('translation', path)
    if not os.path.exists(fp): continue
    with io.open(fp, encoding='utf-8-sig') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        if a is None:
            try: a, b = hdr.index('original'), hdr.index('translation')
            except ValueError: continue
        for line in f:
            p = line.rstrip('\n').split('\t')
            if len(p) > max(a, b) and p[a].strip() and p[b].strip():
                if path.startswith('b10_menu') and p[0] != 'orig': continue
                index_record(p[a], p[b])

by_first = {}
for k in sorted(pairs, key=len, reverse=True):
    by_first.setdefault(k[0], []).append(k)

def split_unmatched(text):
    out, i, buf = [], 0, ''
    while i < len(text):
        hit = None
        for c in by_first.get(text[i], ()):
            if text.startswith(c, i):
                hit = c; break
        if hit:
            if buf: out.append(buf); buf = ''
            i += len(hit)
        else:
            buf += text[i]; i += 1
    if buf: out.append(buf)
    return out

def dec(h):
    o = []
    for i in range(0, len(h), 4):
        try: o.append(bytes.fromhex(h[i:i+4]).decode('shift_jis'))
        except Exception: o.append('?')
    return ''.join(o)

keys = {}
for r in [l.rstrip('\n').split('\t') for l in
          io.open(os.path.join('translation','z11_probe','harvest','harvest.tsv'), encoding='utf-8')][1:]:
    if len(r) >= 4 and r[3]:
        keys.setdefault(r[3], dec(r[3]))

frags = []
for k, jp in keys.items():
    frags.extend(split_unmatched(jp))

print('미매칭 조각 %d개 (고유 %d)' % (len(frags), len(set(frags))))

DIGIT = re.compile(r'[0-9０-９]')
NAMES = ('フェイト', 'シオン')
cat = Counter()
buckets = {}
for f in frags:
    if DIGIT.search(f):            c = '숫자 포함 (자리표시자 치환 추정)'
    elif any(n in f for n in NAMES): c = '인물명 포함 (자리표시자 치환 추정)'
    elif len(f) <= 3:              c = '짧은 라벨 (≤3자)'
    elif len(f) <= 8:              c = '중간 조각 (4~8자)'
    else:                          c = '긴 조각 (9자+)'
    cat[c] += 1
    buckets.setdefault(c, []).append(f)

print('\n=== 분류 ===')
for c, n in cat.most_common():
    print('  %-32s %4d개 (%.0f%%)' % (c, n, 100*n/len(frags)))
    for x in list(dict.fromkeys(buckets[c]))[:5]:
        print('        [%s]' % x[:44])

print('\n자리표시자를 가진 코퍼스 원문: %d종' % len(raw_originals))
for jp, ko in raw_originals[:4]:
    print('   JP %s' % clean(jp).replace('\\n','/')[:60])
    print('   KO %s' % clean(ko).replace('\\n','/')[:60])
