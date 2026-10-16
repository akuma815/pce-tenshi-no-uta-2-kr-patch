# -*- coding: utf-8 -*-
r"""천사의 시 II 스크립트 추출 → 번역 시트 생성 파이프라인.

입력 : extracted/Track02_data.iso  (데이터 트랙 2048B/섹터)
출력 : translation/script_sheet.tsv  (키=ISO오프셋, 원문/번역 대조표)

인코딩 규칙은 구조분석.md §5/§9 참조:
  0x28~0x7A = 히라가나 (SJIS 하위바이트 - 0x77)
  0xA7~0xDD = 반각 가타카나 → 전각
  0x81~     = SJIS 2바이트
  제어: 0x00 종료, 0x0D 줄바꿈(\n), 0x0C 페이지(\p), #n 색상, %d/%x/%s 변수, ~ 커서
"""
import os, sys, collections

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
OUT_DIR = os.path.join(GAME_DIR, "translation")
SEC = 2048
SLOT_BASE, SLOT_SIZE, SLOT_COUNT = 162, 96, 55

# ---- 문자 테이블 ----------------------------------------------------------
KANA = {}
for base, s in [
    (0x28, "ぁあぃいぅうぇえぉお"), (0x32, "かがきぎくぐけげこご"),
    (0x3C, "さざしじすずせぜそぞ"), (0x46, "ただちぢっつづてでとど"),
    (0x51, "なにぬねの"), (0x56, "はばぱひびぴふぶぷへべぺほぼぽ"),
    (0x65, "まみむめも"), (0x6A, "ゃやゅゆょよ"), (0x70, "らりるれろ"),
    (0x75, "ゎわゐゑをん"),
]:
    for i, ch in enumerate(s):
        KANA[base + i] = ch

HALF2FULL = {}
for i, ch in enumerate("。「」、・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソ"
                       "タチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"):
    HALF2FULL[0xA1 + i] = ch

def is_lead(c):  return (0x81 <= c <= 0x9F) or (0xE0 <= c <= 0xEA)
def is_trail(c): return (0x40 <= c <= 0x7E) or (0x80 <= c <= 0xFC)

# ---- 텍스트 런 디코더 ------------------------------------------------------
def decode_run(data, pos, hi):
    out, chars, hira = [], 0, 0
    i = pos
    while i < hi:
        c = data[i]
        if c == 0x0D: out.append("\\n"); i += 1; continue
        if c == 0x0C: out.append("\\p"); i += 1; continue
        if c == 0x0B: out.append("{0B}"); i += 1; continue
        if c == 0x0E: out.append("{0E}"); i += 1; continue
        if c in KANA:
            out.append(KANA[c]); chars += 1; hira += 1; i += 1; continue
        if 0xA1 <= c <= 0xDF:
            out.append(HALF2FULL[c]); chars += 1; i += 1; continue
        if is_lead(c) and i + 1 < hi and is_trail(data[i+1]):
            try:
                out.append(data[i:i+2].decode("shift_jis")); chars += 1; i += 2; continue
            except UnicodeDecodeError:
                pass
        if c in (0x23, 0x25) and i + 1 < hi and 0x21 <= data[i+1] < 0x7F:
            out.append("{%c%c}" % (c, data[i+1])); i += 2; continue
        if c == 0x7E:
            out.append("{~}"); i += 1; continue
        break
    return i, "".join(out), chars, hira

# ---- 영역 분류 -------------------------------------------------------------
def region_of(sec):
    if sec < 2:    return None            # 저작권/IPL
    if sec < 18:   return "boot"
    if sec < SLOT_BASE: return "system"
    if sec < SLOT_BASE + SLOT_SIZE * SLOT_COUNT:
        n = (sec - SLOT_BASE) // SLOT_SIZE
        so = (sec - SLOT_BASE) % SLOT_SIZE
        if 32 <= so < 64:                 # 타일 그래픽 영역
            return None
        return f"slot{n:02d}"
    if sec < 5474: return "misc"
    if 6044 <= sec < 6112: return "card"  # 카드 미니게임
    if sec < 9178: return "late"          # 전투/이벤트 신 프로그램
    return None                            # 제로 테일

# ---- 오탐 필터 -------------------------------------------------------------
BODY_IGNORE = set("\\np{}#%dxs~0123456789BE0")
RARE = set("ゐゑゎぢゥヮ゛゜")
BIGRAMS = set("""
って った てい てる たい たら たり たく ない なく なか なけ なら なり なん なの
のは のに のか のこ のだ のよ のを のも こと この これ ここ こう ころ
です でし ます まし ませ まで でも だが だけ だな だろ だい だっ
から かも かい かな かし かっ かる いる いた いて いう いい いや いつ える えて
んだ んで んな んに んと とい とし とか とも とこ しま して した しい しか
なる なっ にな には にも がい がら があ ある あり あっ あな あの あれ あと
うん おれ おま おい きた きて きっ くだ くれ くる けど けれ さい さん され させ
そう その それ そこ そし ちゃ ちょ つも どう どこ どん どれ はい はず
まだ また まっ みた みて もう もの もん もし やっ やる よう よく よね
らし られ れる れた れば わよ わね わか じゃ たち ばか ぜひ ください
""".split())
PARTICLES = set("はがをにのとでもへや")
PUNCT = set("、。！？「」：…")

def _is_word(ch):
    return ("一" <= ch <= "鿿") or ("゠" <= ch <= "ヿ") \
        or ("０" <= ch <= "ｚ")   # 한자/가타카나/전각영숫자

def naturalness(body):
    score = 0
    for a, b in zip(body, body[1:]):
        if a + b in BIGRAMS: score += 1
        elif _is_word(a) and b in PARTICLES: score += 1
    score += sum(1 for ch in body if ch in PUNCT)
    return score

def looks_dialogue(text, region=""):
    body = [ch for ch in text if ch not in BODY_IGNORE]
    if len(body) < 4:
        return False
    cnt = collections.Counter(body)
    if cnt.most_common(1)[0][1] / len(body) > 0.4 and len(body) > 10:
        return False                       # 동일 문자 반복 = 그래픽
    hira = sum(1 for ch in body if ch in KANA.values())
    if hira < 2 or hira / len(body) < 0.15:
        return False                       # 히라가나 부족 = 그래픽/테이블
    if sum(1 for ch in body if ch in RARE) / len(body) > 0.25:
        return False                       # 희귀 가나 밀집 = 랜덤 데이터
    if "ぁあぃいぅうぇえ" in text:          # 가나 순서 테이블
        return False
    need = 1 if len(body) < 8 else 2
    if region == "late":                   # 그래픽 비중이 큰 영역은 엄격하게
        need = 3
        if hira < 4:
            return False
    return naturalness(body) >= need       # 자연어 점수

# ---- 메인 ------------------------------------------------------------------
def main():
    data = open(ISO, "rb").read()
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c in KANA or (0xA1 <= c <= 0xDF) or is_lead(c):
            j, text, chars, hira = decode_run(data, i, n)
            # 진짜 문자열은 0x00 종결자로 끝난다 (메시지 엔진 규약)
            if chars >= 4 and j < n and data[j] == 0x00:
                reg = region_of(i // SEC)
                if reg and looks_dialogue(text, reg):
                    rows.append((i, reg, text))
                i = j
                continue
            if chars >= 4:
                i = j
                continue
        i += 1

    # 동일 원문 그룹핑 (첫 등장 오프셋 = 그룹 대표)
    first_seen = {}
    for off, reg, text in rows:
        first_seen.setdefault(text, off)

    out_path = os.path.join(OUT_DIR, "script_sheet.tsv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("키(ISO오프셋)\t영역\t중복그룹\t원문\t번역\n")
        for off, reg, text in rows:
            g = first_seen[text]
            dup = "" if g == off else f"={g:07x}"
            f.write(f"{off:07x}\t{reg}\t{dup}\t{text}\t\n")

    # 통계
    per_reg = collections.Counter(reg for _, reg, _ in rows)
    uniq = len(first_seen)
    total_chars = sum(len(t) for _, _, t in rows)
    uniq_chars = sum(len(t) for t in first_seen)
    print(f"rows: {len(rows)}  (unique {uniq})")
    print(f"chars: {total_chars}  (unique {uniq_chars})")
    for reg, cnt in sorted(per_reg.items()):
        print(f"  {reg:8s} {cnt:5d}")
    print(f"-> {out_path}")

if __name__ == "__main__":
    main()
