# -*- coding: utf-8 -*-
r"""기존 번역(translate_original/*)을 script_sheet.tsv에 병합.

- 매칭: 정규화된 일본어 원문 텍스트 (기존 파일은 오프셋 체계가 달라 주소 매칭 불가)
- 우리 행 = 0x00 종결 문자열 (여러 페이지 \p + 화자 포함 가능)
  기존 행 = 창(페이지)/화자 단위 → 페이지·화자로 분해해 매칭 후 재조립
- 산출: script_sheet.tsv 번역 열 채움 + missing_translations.csv (미매칭 고유 원문)
"""
import os, re, csv, collections
import openpyxl

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(GAME_DIR, "translate_original")
TR_DIR = os.path.join(GAME_DIR, "translation")
SHEET = os.path.join(TR_DIR, "script_sheet.tsv")
MISSING = os.path.join(TR_DIR, "missing_translations.csv")

# ---- 정규화 ----------------------------------------------------------------
# 게임 네이티브 마크업(#5 색상, %f0 페이스 등)과 개행/공백을 모두 제거해 비교
_MARKERS = re.compile(r"\\[nepc]|\{[^}]*\}|[%％][sdxfFSDXｓｄｘｆＳＤＸＦ]\d?|[#＃][0-9０-９]|[ \t　~]")
def norm(s):
    s = s.replace("\r", "").replace("\n", "")   # 실제 개행 제거
    s = _MARKERS.sub("", s)
    s = s.replace("\\", "")
    return s

# ---- 기존 번역 로드 ---------------------------------------------------------
def load_sources():
    d = {}       # norm(jp) -> ko
    seq = []     # (norm_jp, ko) 파일 등장 순서 — 빅스트링 폴백용

    def put(jp, ko, override=False):
        if not jp or not ko:
            return
        ko = str(ko).replace("\r", "").replace("\n", "\\n")
        k = norm(str(jp))
        if k and (override or k not in d):
            d[k] = ko
        if k:
            seq.append((k, ko))

    def load_xlsx(name, jp_col, ko_col, override=False):
        path = os.path.join(SRC_DIR, name)
        if not os.path.exists(path):
            return
        wb = openpyxl.load_workbook(path, read_only=True)
        for row in wb.worksheets[0].iter_rows(min_row=2, values_only=True):
            put(row[jp_col], row[ko_col], override)
        wb.close()

    load_xlsx("천사의시2_대사_번역.xlsx", 2, 4)
    load_xlsx("천사의시2_3줄초과_수정필요.xlsx", 2, 4, override=True)  # 수정본 우선
    load_xlsx("천사의시2_크레딧_번역.xlsx", 1, 3)
    load_xlsx("천사의시2_UI_번역.xlsx", 2, 4)

    path = os.path.join(SRC_DIR, "visualscene2_paired.csv")
    if os.path.exists(path):
        for row in csv.DictReader(open(path, encoding="utf-8-sig")):
            put(row.get("jp"), row.get("ko"))

    # 사용자 추가 번역 (translation/output/*.tsv, jp\tko 형식) — 최우선 적용
    #  - ko == jp : "노이즈 확인" 표시 → ignore 집합에 넣어 missing에서 제외
    #  - ko 비어있음 / ko에 가나 잔존(미완성) → 건너뜀 (missing에 유지)
    out_dir = os.path.join(TR_DIR, "output")
    kana_re = re.compile(r"[ぁ-ゖァ-ヺ]")
    ignore = set()
    n_user = 0
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".tsv"):
                continue
            with open(os.path.join(out_dir, name), encoding="utf-8-sig") as f:
                header = f.readline().rstrip("\n").split("\t")
                try:
                    ij, ik = header.index("jp"), header.index("ko")
                except ValueError:
                    continue
                for line in f:
                    cols = line.rstrip("\n").split("\t")
                    if len(cols) <= max(ij, ik):
                        continue
                    jp, ko = cols[ij], cols[ik]
                    if ko == jp:
                        ignore.add(norm(jp))
                        continue
                    if not ko or kana_re.search(ko):
                        continue
                    put(jp, ko, override=True)
                    n_user += 1
    print(f"user translations from output/: {n_user}  (noise-confirmed: {len(ignore)})")
    return d, seq, ignore

# ---- 빅스트링 폴백: 분할 단위가 어긋난 조각을 부분문자열로 매칭 -----------------
class BigString:
    def __init__(self, seq):
        self.spans = []          # (start, end, ko)
        pos = 0
        for k, ko in seq:
            self.spans.append((pos, pos + len(k), ko))
            pos += len(k)
        self.text = "".join(k for k, _ in seq)

    def find(self, k):
        if len(k) < 6:
            return None
        p = self.text.find(k)
        if p < 0:
            return None
        q = p + len(k)
        hit = [(s, e, ko) for s, e, ko in self.spans if s < q and e > p]
        if not hit:
            return None
        if len(hit) == 1:
            s, e, ko = hit[0]
            if (len(k)) / (e - s) >= 0.90:   # 텍스트 손실 방지: 거의 전체 커버만 허용
                return ko
            return None
        # 여러 행에 걸침: 경계가 행 경계와 정확히 일치할 때만 (±1자)
        if abs(hit[0][0] - p) <= 1 and abs(hit[-1][1] - q) <= 1:
            return "\\n".join(ko for _, _, ko in hit)
        return None

# ---- 조회 (쓰레기 접두 1~8자 허용 + 빅스트링 폴백) -----------------------------
def lookup(d, big, piece, max_cut=None):
    """max_cut: 쓰레기 접두 절단 허용치. None이면 남는 길이 6자까지 무제한.
    행 전체 매칭에는 작은 값(8)을 써야 다중 페이지가 꼬리 페이지에 오매칭되지 않는다."""
    k = norm(piece)
    if not k:
        return "", True          # 마커뿐인 조각은 그대로 통과
    if k in d:
        return d[k], True
    limit = (len(k) - 5) if max_cut is None else min(max_cut + 1, len(k))
    for cut in range(1, max(1, limit)):
        if k[cut:] in d:
            return d[k[cut:]], True
    for cut in range(0, 3):      # 빅스트링은 접두 절단을 보수적으로
        if cut < len(k):
            ko = big.find(k[cut:])
            if ko:
                return ko, True
    return "", False

# ---- ko 새니타이저: 기존 번역 ko에 포함된 마크업/화자 헤더 중복 제거 ------------
_KO_HEAD = re.compile(r"^(?:[%％][fF]\d|[#＃]\d|\\n)+")
_KO_SPK = re.compile(r"^[^：:\\{}\n]{1,12}[：:]")
def strip_ko_header(ko, with_speaker):
    s = _KO_HEAD.sub("", ko)
    if with_speaker:
        m = _KO_SPK.match(s)
        if m:
            s = s[m.end():]
            s = _KO_HEAD.sub("", s)
    return s

# ---- 우리 행 분해/재조립 ------------------------------------------------------
_HEAD = re.compile(r"^((?:\\n|\{[^}]*\})*)(.*)$", re.S)

def translate_row(text, d, big):
    """전 조각 매칭 성공 시 (번역문, []), 실패 시 ("", [미매칭 조각들])"""
    ko, ok = lookup(d, big, text, max_cut=8)   # 행 전체 일치 우선 (절단 제한)
    if ok and ko:
        return ko, []
    out_pages, miss = [], []
    for page in text.split("\\p"):
        markers, rest = _HEAD.match(page).groups()
        # 1차: 페이지 전체 매칭 (기존 파일 행 = 화자 포함 페이지 단위)
        page_ko, ok = lookup(d, big, rest)
        if ok:
            out_pages.append(page_ko if norm(rest) else markers)
            continue
        # 2차: 화자/본문 분리 매칭
        idx = rest.find("：")
        if 0 < idx <= 14:
            spk_raw, body = rest[:idx], rest[idx + 1:]
            spk_ko, ok1 = lookup(d, big, spk_raw)
            m2, body2 = _HEAD.match(body).groups()
            body_ko, ok2 = lookup(d, big, body2, max_cut=2)  # 본문은 깨끗하게 시작
            if ok1 and ok2:
                spk_ko = strip_ko_header(spk_ko, False).rstrip("：:")
                body_ko = strip_ko_header(body_ko, True)
                out_pages.append(f"#5{spk_ko}：\\n#1{body_ko}")
            else:
                if not ok1: miss.append(norm(spk_raw))
                if not ok2: miss.append(norm(body2))
        else:
            miss.append(norm(rest))
    if miss:
        return "", miss
    return "\\p".join(out_pages), []

# ---- 메인 -------------------------------------------------------------------
def main():
    d, seq, ignore = load_sources()
    big = BigString(seq)
    print(f"loaded translations: {len(d)} (seq {len(seq)})")

    lines = open(SHEET, encoding="utf-8-sig").read().splitlines()
    header, rows = lines[0], [l.split("\t") for l in lines[1:]]

    filled = 0
    missing = {}         # 원문 -> (첫 키, 영역, 미매칭조각, 등장횟수)
    cache = {}
    for r in rows:
        off, reg, dup, text = r[0], r[1], r[2], r[3]
        if text in cache:
            ko, miss = cache[text]
        else:
            ko, miss = translate_row(text, d, big)
            cache[text] = (ko, miss)
        r[4] = ko            # 매 실행마다 재생성 (이전 채움 잔존 방지)
        if ko:
            filled += 1
        elif norm(text) in ignore:
            pass             # 사용자가 노이즈로 확인한 행
        elif text not in missing:
            missing[text] = [off, reg, " / ".join(dict.fromkeys(miss)), 1]
        else:
            missing[text][3] += 1

    with open(SHEET, "w", encoding="utf-8-sig", newline="") as f:
        f.write(header + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    with open(MISSING, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["키(ISO오프셋)", "영역", "등장횟수", "미매칭조각", "원문", "번역"])
        for text, (off, reg, miss, cnt) in sorted(missing.items(), key=lambda kv: kv[1][0]):
            w.writerow([off, reg, cnt, miss, text, ""])

    uniq_total = len(cache)
    uniq_missing = len(missing)
    print(f"rows: {len(rows)}  filled: {filled} ({filled/len(rows)*100:.1f}%)")
    print(f"unique texts: {uniq_total}  translated: {uniq_total-uniq_missing}  missing: {uniq_missing}")
    print(f"-> {SHEET}")
    print(f"-> {MISSING}")

if __name__ == "__main__":
    main()
