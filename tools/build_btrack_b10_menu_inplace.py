#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B10 — 메뉴/전투/비주얼/비씬 대사 제자리 치환 + 테이블 재패킹.

원리 (b10poc 로 런타임 실증): 카드 폰트가 SJIS 한자 슬롯을 한글로 바꿔
두므로, **원문 레코드를 한글 슬롯 SJIS 로 치환**하면 어떤 렌더러든 훅
없이 한글이 나온다. Z8 인코딩(한글 2B)과 길이 산정이 동일하다.

두 가지 모드:
  1. **테이블 재패킹** (이름류 — 2026-08-28 포인터 실증): 연속 레코드 런의
     시작 오프셋 열과 delta 가 정확히 일치하는 u16 포인터 테이블이 같은
     모듈에 존재하면(전 엔트리 검증), 문자열 블록을 KO 로 재패킹하고
     포인터를 재작성한다 — 개별 레코드 길이 제한이 사라지고 블록 총량만
     지키면 된다(시온·몬스터명 등 1~2B 초과 문제 해소). 재작성 후 모듈
     내에 옛 레코드 주소를 가리키는 잔여 u16 이 남으면 fail-closed 로
     그 런을 재패킹 제외(보고).
  2. **고정길이 제자리** (포인터 미발견 런·단독 레코드): 같은 길이 이하일
     때만 치환, 잔여 00 패딩.

대상 (ziria_z8_text_entry_index.csv):
  - family ∈ {menu_memo_system, battle, visual_event_portrait}
  - family == dialogue_event 이면서 54씬 extent **밖** (부트 모듈·
    shared.visual_event 자막·primary 컨테이너 — b9 카드 서브 비대상)
필터: 번역 없음/원문 동일/일문 포함 행 제외 (원문 유지 = 안전 폴백).
부적합 행은 `b10_menu_overrides.tsv` 의 짧춤 번역(id→ko)으로 재시도,
그래도 안 되면 원문 유지 + worklist 보고.

출력: translation/btrack_b10_menu_patches.json
      translation/btrack_b10_menu_worklist.tsv (부적합 행 — 짧춤 검토용)
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_ziria_z8_text_containers import strict_encode
import build_ziria_z8_text_containers as _z8c
# (2026-10-11 b52) 「・」는 원문처럼 2바이트 0x8145 로 — 반각 0xA5 는 이 엔진의 1바이트 표(A7-DD) 밖이라 표시 근거가 없다.
#   말줄임 「...」(전각 ．．． 2B×3) → 「・・・」(2B×3) 와 길이 같음.
_z8c.HALF2FULL.pop("・", None)

ENTRY_INDEX = ROOT / "translation" / "ziria_z8_text_entry_index.csv"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
OVERRIDES = ROOT / "translation" / "b10_menu_overrides.tsv"
PREFER_FULL = ROOT / "translation" / "b10_prefer_full.txt"
UNINDEXED_BATTLE = ROOT / "translation" / "b10_unindexed_battle.tsv"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
# b14 (2026-10-09): 환경변수 B10_OUT_TAG 가 있으면 출력 이름을 바꾸고(b10 입력 보존),
# B10_EXTRA_IDS 가 가리키는 파일의 id 들을 대상에 추가한다(보류 클래스 편입).
import os as _os
_TAG = _os.environ.get("B10_OUT_TAG", "b10")
OUT_PATCHES = ROOT / "translation" / f"btrack_{_TAG}_menu_patches.json"
OUT_FINAL_TEXT = ROOT / "translation" / f"btrack_{_TAG}_menu_final_text.json"   # (2026-10-11) 행별 최종 문구 — 줄임말 감사용
FINAL_TEXT: dict = {}
OUT_WORKLIST = ROOT / "translation" / f"btrack_{_TAG}_menu_worklist.tsv"
OUT_PLACEMENTS = ROOT / "translation" / f"btrack_{_TAG}_arena_placements.json"
EXTRA_IDS_FILE = _os.environ.get("B10_EXTRA_IDS")

SCENE_EXTENT = (290 * 2048, (5378 + 96) * 2048)   # 54씬 오버레이 구간
FAMILIES_ALL = {"menu_memo_system", "battle", "visual_event_portrait"}

# 메모 목록 헤더 — b9 비소유이고 제어 접두(0xC0 열) 때문에 번역이 비어
# 있던 행. 포인터 타깃이 아니라서 memo_ptr_ids 로는 안 잡힌다.
MEMO_EXTRA_ORIGINALS = {"タあタおタごタぜタとタひタ次の目的のこと"}


def has_japanese(t: str) -> bool:
    # (2026-10-11 b52) 「・」(U+30FB)는 문장부호 — 말줄임 「・・・」 번역문이 일문으로 오판돼 짧은 폴백으로 떨어지던 것 제외
    return any((("぀" <= c <= "ヿ") and c != "・") or ("一" <= c <= "鿿")
               for c in t)


# `{%f}` 뒤 한 글자는 **초상화 번호 파라미터**다 (원본 바이트 25 66 31 —
# 추출기가 1바이트 값 0x31 을 'お' 로 디코드한 것). 본문이 아니므로 일문
# 검사에서 제외한다. 2026-08-30: 이 오판 때문에 초상화 4,083행이 전부
# '일문 포함' 으로 걸러지고 있었다.
_PORTRAIT_PARAM = re.compile(r"(\{%f\})(.)")
# 메모 목록 헤더처럼 **제어 바이트 0xC0 시퀀스**가 'タ<가나>' 로 디코드된
# 접두. 접두를 뺀 본문만 일문 검사한다 (인코더는 원 바이트를 복원한다 —
# 원문 재인코딩 == ISO raw 로 실증).
_CTRL_PREFIX = re.compile(r"^(?:タ.)+")


def text_only(t: str) -> str:
    """일문 검사용: 파라미터·제어 접두를 제거한 본문."""
    return _CTRL_PREFIX.sub("", _PORTRAIT_PARAM.sub(r"\1", t))


# 반각 ASCII 는 shift_jis 폴백으로 1바이트가 되는데, 게임의 1바이트
# 차셋은 압축 가나라 'HP' 가 'ちど' 로 렌더된다 (2026-08-29 상태창 실측).
# → 토큰(\n·\p·{...}) 밖 자유 텍스트의 ASCII 를 전각으로. 반각 스페이스는
# 기존 번역 스타일(무공백)에 맞춰 제거 — 전각화하면 수천 행이 길이 초과.
_TOK_SPLIT = re.compile(r"(\\n|\\p|\{[^}]{1,3}\})")


def fullwidth(text: str) -> str:
    parts = _TOK_SPLIT.split(text)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append(p)
            continue
        out.append("".join(
            "" if c == " " else
            chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c
            for c in p))
    return "".join(out)


def find_pointer_tables(iso: bytes, offs: list[int]):
    """1차: 레코드 시작열과 delta 전 엔트리 일치 u16 테이블(원 순서).
    반환 [(테이블오프셋, base)] — base = 레코드0 의 논리주소."""
    n = len(offs)
    lo = max(0, offs[0] - 0x20000)
    hi = min(len(iso) - 2 * n, offs[-1] + 0x20000)
    hits = []
    rel = [o - offs[0] for o in offs]
    for i in range(lo, hi):
        base = iso[i] | (iso[i + 1] << 8)
        ok = True
        for k in range(1, n):
            v = iso[i + 2 * k] | (iso[i + 2 * k + 1] << 8)
            if v - base != rel[k]:
                ok = False
                break
        if ok:
            hits.append((i, base))
    return hits


def find_extra_tables(iso: bytes, offs: list[int], base: int,
                      primary_spans: list[tuple[int, int]]):
    """2차: 옛 레코드 주소 집합만으로 구성된 연속 u16 배열(임의 순서 —
    정렬 메뉴 등). ≥3 연속이면 테이블로 인정해 재작성 대상에 넣는다.
    고립 일치는 통계적으로 대부분 우연(u16 충돌)이라 기각 사유로 쓰지
    않고 개수만 보고한다 — 진짜 단독 참조가 있었다면 표시 어긋남(비파괴)
    으로 게이트에서 드러난다. 스캔은 런 주변 ±0x1000 (테이블은 실측상
    문자열 바로 앞 수백 바이트에 있음)."""
    old_ptrs = {base + (o - offs[0]) for o in offs}
    lo = max(0, offs[0] - 0x1000)
    hi = min(len(iso) - 2, offs[-1] + 0x1000)
    tables = []
    strays = []
    i = lo
    while i < hi:
        if any(s <= i < e for s, e in primary_spans):
            i += 1
            continue
        v = iso[i] | (iso[i + 1] << 8)
        if v in old_ptrs:
            j = i
            vals = []
            while j < hi:
                w = iso[j] | (iso[j + 1] << 8)
                if w not in old_ptrs:
                    break
                vals.append(w)
                j += 2
            if len(vals) >= 3:
                tables.append((i, vals))
            else:
                strays.append(i)
            i = j + 1
        else:
            i += 1
    return tables, strays


def main() -> None:
    csv.field_size_limit(10 ** 7)
    iso = ISO.read_bytes()
    doc = json.loads(ASSIGN.read_text(encoding="utf-8"))
    glyph_map = {ch: e["sjis"] for ch, e in doc["assignment"].items()}
    overrides = {}          # id -> ko
    orig_overrides = {}     # 원문 텍스트 -> ko (전 사본 공통 적용)
    # 표기 통일(사용자 결정 2026-08-29): 대사 표기를 우선하고, 제자리
    # 길이에 안 맞을 때만 짧춤으로 폴백할 원문 집합
    prefer_full = set()
    if PREFER_FULL.is_file():
        prefer_full = {ln for ln in
                       PREFER_FULL.read_text(encoding="utf-8").splitlines()
                       if ln.strip()}
    if OVERRIDES.is_file():
        with OVERRIDES.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("key_type") == "orig":
                    orig_overrides[r["key"]] = r["ko"]
                else:
                    overrides[r["key"]] = r["ko"]
    # b16 (2026-10-09): 용어 통일 — 모든 orig 오버라이드(축약)는 **전체 표기가 들어가면
    # 전체 표기**, 안 들어갈 때만 축약(폴백). 사용자: "습득 땐 떡갈나무 방패, 장비창은
    # 목방패 — 통일 필요". 1바이트 코드로 대부분 전체 표기가 들어간다.
    if _os.environ.get("B10_PREFER_FULL_ALL"):
        prefer_full |= set(orig_overrides)

    rows = list(csv.DictReader(ENTRY_INDEX.open(encoding="utf-8-sig",
                                                newline="")))
    # 씬 내 dialogue 행 중 b9(카드 서브) 소유 레코드는 제외하되,
    # **공유 블록 UI**(동일 원문·길이가 10+ 씬 사본으로 반복 — 使う/右 류)
    # 는 b9 비대상(비인라인)이므로 b10 이 소유한다 (2026-08-29 게이트 갭).
    from collections import Counter
    from build_btrack_b9_hook_build import SCENES_B9
    from build_btrack_b9_hook_build import payload as b9_payload
    b9_ids: set[str] = set()
    # 메모 목록은 **씬 패키지 RAM 을 직접 읽는다**(2026-08-30 실증: 메모
    # 화면 세이브스테이트 RAM 뱅크 $7F 에 원문 바이트가 그대로 있고 ISO
    # 0xA100B 와 일치, zp $53=C0 라 armchk 가 서브를 거부). b9 가 소유해도
    # 화면에 안 나오므로 **b10 이 디스크에서 제자리 치환**해야 한다.
    memo_ptr_ids: set[str] = set()
    for lba in SCENES_B9:
        for rec in b9_payload(lba):
            b9_ids.add(rec["id"])
            if rec.get("reference_kind") == "MEMO_POINTER_TARGET":
                memo_ptr_ids.add(rec["id"])
    incount: Counter = Counter()
    for r in rows:
        off = int(r["iso_offset"], 16)
        if r["family"] == "dialogue_event" \
                and SCENE_EXTENT[0] <= off < SCENE_EXTENT[1]:
            incount[(r["original"], r["raw_length"])] += 1
    # b9 payload 는 master 로 dedupe 돼 있어 id 집합만 쓰면 **일부 씬 사본이
    # 누락**된다(2026-08-30: 54사본 중 1곳이 안 잡혀 그 씬 메모가 일문).
    # 원문 텍스트로 확장해 전 사본을 포함시킨다.
    memo_originals = set(MEMO_EXTRA_ORIGINALS)
    memo_originals.update(r["original"] for r in rows
                          if r["id"] in memo_ptr_ids)
    extra_ids: set[str] = set()
    if EXTRA_IDS_FILE:
        extra_ids = {ln.strip() for ln in Path(EXTRA_IDS_FILE).read_text(
            encoding="utf-8").splitlines() if ln.strip()}
    targets = []
    for r in rows:
        fam = r["family"]
        off = int(r["iso_offset"], 16)
        if r["id"] in extra_ids:
            targets.append(r)
            continue
        in_scene = SCENE_EXTENT[0] <= off < SCENE_EXTENT[1]
        if fam in FAMILIES_ALL or (fam == "dialogue_event" and not in_scene):
            targets.append(r)
        elif fam == "dialogue_event" and in_scene \
                and r["original"] in memo_originals:
            # 메모 목록(포인터 타깃 + 목록 헤더) = b9 소유여도 디스크
            # 제자리 치환 대상 (위 주석의 RAM 직접 읽기 실증)
            targets.append(r)
        elif fam == "dialogue_event" and in_scene \
                and incount[(r["original"], r["raw_length"])] >= 10 \
                and r["id"] not in b9_ids \
                and (r["subcategory"] == "event_dialogue_or_command"
                     or r["original"] in ("フェイトは宝箱を開けた",
                                          "何も入っていない。")):
            # 1차 범위: UI 명령·상자 메시지 클래스만. 씬 상주 후반 몬스터명
            # (asset_confirmed_short_event_text 블록)은 전용 패스로 —
            # 창 부족 ~100B/창 × 40창의 짧춤 검토가 선행돼야 함 (worklist).
            targets.append(r)
    targets.sort(key=lambda r: int(r["iso_offset"], 16))

    # b15 (2026-10-09): 1바이트 한글 코드. 엔진/메뉴 모듈의 카타카나 디코더는
    # [lead,trail] 테이블($A7+i → 2바이트)이라 테이블만 바꾸면 코드 $A7.. 가 한글
    # 글리프 슬롯을 가리킨다. B10_ONEBYTE_MAP(json) 이 있으면 그 음절은 1바이트로
    # 인코드한다. 범위 = B10_ONEBYTE_SCOPE: names(기본, 보류 클래스+monster_names) | all.
    onebyte: dict[str, int] = {}
    if _os.environ.get("B10_ONEBYTE_MAP"):
        _m = json.loads(Path(_os.environ["B10_ONEBYTE_MAP"]).read_text(encoding="utf-8"))["map"]
        onebyte = {v["ch"]: int(code, 16) for code, v in _m.items()}
    onebyte_scope = _os.environ.get("B10_ONEBYTE_SCOPE", "names")

    def _enc_onebyte(text: str) -> bytes:
        out = bytearray()
        seg = ""
        for ch in text:
            if ch in onebyte:
                if seg:
                    out.extend(strict_encode(seg, glyph_map))
                    seg = ""
                out.append(onebyte[ch])
            else:
                seg += ch
        if seg:
            out.extend(strict_encode(seg, glyph_map))
        return bytes(out)

    # b18 (2026-10-09): `{%s}` 직후 조사(은/는·이/가·을/를·과/와) → 마커 1F + 종류 (런타임 가변 생성,
    # 리더 v4 + 카드 조사 루틴). 길이 동일(2B). B10_JOSA=1 일 때만.
    import re as _re
    JOSA_RE = _re.compile(r"(\{%s\})(은|는|이|가|을|를|과|와)")
    JOSA_TYPE = {"은": 0, "는": 0, "이": 1, "가": 1, "을": 2, "를": 2, "과": 3, "와": 3}
    use_josa = bool(_os.environ.get("B10_JOSA"))
    JOSA_TRAILING_SPACE = _os.environ.get("B10_JOSA_SPACE") == "1"   # b34: 카드 조사 문자열에 전각 공백 포함
    use_space = _os.environ.get("B10_SPACE") == "half"
    SPACE_SUBCATS = {"system_menu_battle", "event_dialogue_or_command",
                     "asset_confirmed_event_text", "asset_confirmed_short_event_text",
                     "menu_and_shop_commands"}

    def _enc_core(text, use1):
        if use1:
            return _enc_onebyte(text)
        return strict_encode(text, glyph_map)

    def _enc(ko, r=None):
        if has_japanese(text_only(ko)):
            return None
        use1 = bool(onebyte) and r is not None and (
            onebyte_scope == "all"
            or r["id"] in extra_ids or r["subcategory"] == "monster_names")
        try:
            text = fullwidth(ko)
            if use_josa and JOSA_RE.search(text):
                out = bytearray()
                pos = 0
                for m in JOSA_RE.finditer(text):
                    out += _enc_core(text[pos:m.end(1)], use1)      # … + {%s}
                    out += bytes((0xA0 + JOSA_TYPE[m.group(2)],))       # 마커 $A0+종류 (1B) — 텍스트에 못 나오는 값
                    pos = m.end()
                    # (2026-10-10 b34) 카드의 조사 문자열이 「를　」처럼 뒤 공백을 품는다 → 템플릿 쪽 공백은 버린다(바이트 절약).
                    if JOSA_TRAILING_SPACE:
                        for tok in ("{~}", "　", " "):
                            if text.startswith(tok, pos):
                                pos += len(tok); break
                out += _enc_core(text[pos:], use1)
                return bytes(out) + b"\x00"
            return _enc_core(text, use1) + b"\x00"
        except ValueError:
            return None

    def encoded(r, limit=None):
        """(ko, enc+NUL) 또는 (ko, None=인코드불가/제외).

        **표기 통일(prefer_full)** 대상은 대사 쪽 전체 표기를 우선한다.
        고정길이 제자리(limit 지정)에서 전체 표기가 안 들어가면 짧춤
        오버라이드로 폴백한다 — 폴백이 없으면 일문으로 되돌아가므로
        (2026-08-29 실측 NOFIT +62) 반드시 이 순서를 지킬 것.
        """
        short = overrides.get(r["id"]) or orig_overrides.get(r["original"])
        tr = r["translation"] or ""
        # 오버라이드가 있으면 same_as_original(미번역) 행도 구제한다 —
        # 메모 목록 헤더처럼 제어 접두 때문에 번역이 비어 있던 경우.
        if not short and (not tr or r["same_as_original"] == "yes"):
            return None, None
        # b18 (2026-10-09) 띄어쓰기: B10_SPACE=half 면 메시지 클래스의 반각 스페이스를 반칸 토큰 {~}(1B)로
        # 살린다. 제자리 슬롯(또는 raw_length)에 안 들어가면 종전대로 공백 제거. `{%s}` 바로 뒤의 공백은
        # {~} 지연 적용 버그(Z10 §2.16) 때문에 전각 공백(2B)으로. 레이아웃 레코드(상태창·메뉴 표)는 제외.
        def _half_ok(nxt2, prev=""):
            # (2026-10-11 게이트 「마랑루시에드의공 격」 = {%s}의(1B DB){~}공격) 반칸 **앞** 글자가 1바이트 코드여도 늦게 찍힌다 → 앞 글자도 검사.
            if prev and prev in onebyte:
                return False
            return len(nxt2) == 2 and all(("가" <= c <= "힣") and c not in onebyte for c in nxt2)

        def _with_space(ko, smart=True):
            if not use_space or r["subcategory"] not in SPACE_SUBCATS or " " not in ko:
                return None
            t = ko.replace("{%s} ", "{%s}　")
            # b27 (2026-10-10): 반칸 {~} 는 한 글자 늦게 적용되는 엔진 버그가 있어, 다음 글자가 1바이트 코드면
            # (1바이트 경로가 보류된 반칸을 소비하지 않아 「셰이드루 비」) 전각 공백(2B)으로 둔다.
            # (2026-10-10 게이트 실측) 반칸이 제자리에 찍힌 경우는 모두 **뒤 두 글자가 2바이트**였다(「아직 눈치」「눈치 못」).
            #  뒤 두 글자 안에 1바이트 코드가 있으면 늦게 찍힌다(「셰이드루 비」, 「못챘 다」) → 그때는 전각 공백(2B).
            out = []
            for i, ch in enumerate(t):
                if ch == " ":
                    out.append("{~}" if _half_ok(t[i + 1:i + 3], t[i - 1] if i else "") else "　")
                else:
                    out.append(ch)
            return "".join(out)

        def _partial(ko, cap):
            """(2026-10-10) 전부 넣으면 넘칠 때: 예산 안에서 공백을 일부만 살린다. 가장 긴 무공백 구간을
            가운데서 끊는 공백부터 하나씩 시도(넣어서 넘치면 그 공백만 포기)."""
            if not use_space or r["subcategory"] not in SPACE_SUBCATS or " " not in ko:
                return None
            words = ko.split(" ")
            def sep(i):
                if words[i - 1].endswith("{%s}") or not _half_ok(words[i][:2], words[i - 1][-1:]):
                    return "　"
                return "{~}"
            def build(keep):
                out = [words[0]]
                for i in range(1, len(words)):
                    out.append((sep(i) if i in keep else "") + words[i])
                return "".join(out)
            def hl(t):
                t = re.sub(r"\{[^}]*\}", "", t)
                return max((sum(1 for c in seg if "가" <= c <= "힣") for seg in re.split(r"\\[np]", t)), default=0)
            keep, pool = set(), set(range(1, len(words)))
            best = None
            while pool:
                # 현재 구간들 중 가장 긴 구간 안의 후보를, 구간 가운데에 가까운 순으로
                bounds = [0] + sorted(keep) + [len(words)]
                segs = sorted(((hl("".join(words[a:b])), a, b) for a, b in zip(bounds, bounds[1:])), reverse=True)
                cand = None
                for _, a, b in segs:
                    inside = [i for i in pool if a < i < b]
                    if inside:
                        mid = (a + b) / 2
                        cand = min(inside, key=lambda i: abs(i - mid)); break
                if cand is None:
                    break
                pool.discard(cand)
                t = build(keep | {cand}); e = _enc(t, r)
                if e is not None and len(e) <= cap:
                    keep.add(cand); best = (t, e)
            return best

        def _try(ko):
            # (2026-10-10) limit=None = 포인터 런(아레나 재배치) 행: 원문 길이 제한 없이 띄어쓰기 판을 쓴다.
            #  창이 넘치면 아래 '최소 축약' 루프가 encoded(r, limit=0)(공백 없는 판/축약)으로 하나씩 되돌린다.
            if limit is None:
                sp = _with_space(ko, True)
                if sp is not None:
                    e = _enc(sp, r)
                    if e is not None:
                        return sp, e
            cap = limit if limit is not None else int(r["raw_length"])
            for smart in (True,):   # (2026-10-10) smart=False(전부 반칸) 폴백 제거 — 늦게 찍히는 반칸을 만들었다
                sp = _with_space(ko, smart)
                if sp is not None:
                    e = _enc(sp, r)
                    if e is not None and len(e) <= cap:
                        return sp, e
            pp = _partial(ko, cap)
            if pp is not None:
                return pp
            return ko, _enc(ko, r)

        if r["original"] in prefer_full:
            ko2, enc = _try(tr)
            if enc is not None and (limit is None or len(enc) <= limit):
                return ko2, enc
            if short:
                return _try(short)
            return ko2, enc
        ko = short or tr
        return _try(ko)

    def ko_of(r):
        return (encoded(r)[0] or "")

    patches = []
    worklist = []
    stats = {"target_rows": len(targets), "arena_windows": 0,
             "arena_runs": 0, "arena_rows": 0, "run_rejected_stray_ptr": 0,
             "run_no_table": 0, "arena_overflow_rows": 0,
             "extra_tables_rewritten": 0,
             "inplace_patched": 0, "kept_original_nofit": 0,
             "kept_original_jp_or_encode": 0, "skipped_same_or_empty": 0,
             "override_used": 0, "donor_tail_bytes": 0}

    # ---- 1) 포인터 런 발굴 --------------------------------------------------
    groups: dict[tuple[str, str], list] = {}
    for r in targets:
        groups.setdefault((r["package_id"], r["subcategory"]), []).append(r)
    pruns = []          # {rows, offs, lens, tables:[(toff, base|vals, kind)]}
    consumed: set[str] = set()
    # b15 (2026-10-09): 재배치 금지 서브카테고리. 배틀 모듈이 몬스터명을 창 포인터
    # 테이블이 아닌 다른 경로(원 주소)로 읽는다 — 재배치하면 이름이 빈 채 '출현!'
    # (사용자 스크린샷). b10 기록대로 몬스터명 포인터 테이블은 정적으로 못 찾았다.
    # 이 서브카테고리는 **제자리 치환만**(1바이트 코드로 대부분 적합, 나머지 축약 폴백).
    NO_RELOC = {s for s in _os.environ.get("B10_NO_RELOC_SUBCATS", "").split(",") if s}
    noreloc_offs: set[int] = set()
    for (pkg, sub), grp in sorted(groups.items()):
        if sub in NO_RELOC:
            continue
        grp.sort(key=lambda r: int(r["iso_offset"], 16))
        runs, cur = [], [grp[0]]
        for a, b in zip(grp, grp[1:]):
            if int(a["iso_offset"], 16) + int(a["raw_length"]) == \
                    int(b["iso_offset"], 16):
                cur.append(b)
            else:
                runs.append(cur)
                cur = [b]
        runs.append(cur)
        for run in runs:
            if len(run) < 4:
                continue
            offs = [int(r["iso_offset"], 16) for r in run]
            lens = [int(r["raw_length"]) for r in run]
            prim = find_pointer_tables(iso, offs)
            if not prim:
                stats["run_no_table"] += 1
                continue
            bases = {b for _, b in prim}
            # base 가 여러 개 = 같은 문자열이 서로 다른 창 매핑에서 참조됨
            # → 자기 extent 안에서만 재배치(모든 창에서 유효)하는 self 모드
            self_mode = len(bases) != 1
            base = prim[0][1]
            spans = [(t, t + 2 * len(run)) for t, _ in prim]
            extra, strays = find_extra_tables(iso, offs, base, spans)
            stats["stray_u16_noted"] = stats.get("stray_u16_noted", 0) \
                + len(strays)
            # 전 행 인코딩 가능해야 아레나 참여 (부분 참여는 포인터 정합 붕괴)
            encs = []
            ok = True
            for r in run:
                ko, enc = encoded(r)
                FINAL_TEXT[r["id"]] = {"path": "arena", "ko": ko}
                if enc is None:
                    ok = False
                    break
                encs.append(enc)
            if not ok:
                stats["run_no_table"] += 1   # 원문 유지
                worklist.append((f"RUN:{pkg}:{sub}@{offs[0]:07X}", sub,
                                 sum(lens), -1, f"{len(run)} rows", "",
                                 "ENCODE_IN_RUN"))
                continue
            pruns.append({"pkg": pkg, "sub": sub, "rows": run, "offs": offs,
                          "lens": lens, "base": base, "encs": encs,
                          "prim": prim, "extra": extra, "self": self_mode,
                          "strays": strays})
            consumed.update(r["id"] for r in run)

    # (2026-10-10) 가짜 1차 테이블 기각: 짧은 런(4행 등)의 레코드 간격 패턴이 **다른(더 긴) 런의 실제 테이블 일부**와
    #  우연히 일치하면 그 자리를 자기 테이블로 오인해 덮어쓴다(장비 창 「기도의 방패」 공백 사건, b30 PTR_FIX 11건의 원인).
    #  다른(더 긴) 런의 테이블 구간과 겹치는 후보는 버린다(더 긴 테이블 쪽이 진짜). 후보가 모두 버려지면 런 자체는 유지
    #  (나머지 진짜 테이블로 재작성).
    _spans = [(pr_i, t, t + 2 * len(pr["rows"])) for pr_i, pr in enumerate(pruns) for t, _ in pr["prim"]]
    for pr_i, pr in enumerate(pruns):
        n = len(pr["rows"]); keep = []
        for t, b in pr["prim"]:
            inside_other = any(j != pr_i and t < s1 and s0 < t + 2 * n and (s1 - s0) > 2 * n for j, s0, s1 in _spans)   # 더 긴 테이블과 겹침
            if inside_other:
                stats["fake_table_rejected"] = stats.get("fake_table_rejected", 0) + 1
                print(f"  가짜 테이블 기각: 런 {pr['offs'][0]:07X}({n}행) 후보 @{t:07X}", flush=True)
            else:
                keep.append((t, b))
        if keep and len(keep) != len(pr["prim"]):
            pr["prim"] = keep
            bases = {b for _, b in keep}
            pr["self"] = len(bases) != 1
            pr["base"] = keep[0][1]

    # ---- 2) 고정길이 제자리 (포인터 런 밖 행) — 창별 도너 꼬리 수집 ----------
    inplace = []        # (off, raw_len, enc)
    nofit_pool = []     # 제자리 초과 — 창 재배치 후보 (off, rl, enc, ko, row)
    extra_ptr_sites: dict[int, list] = {}   # 미인덱스 보충의 실측 포인터
    seen_offsets: dict[int, str] = {}
    for r in targets:
        if r["id"] in consumed:
            continue
        off = int(r["iso_offset"], 16)
        raw = bytes.fromhex(r["raw_hex"])
        assert iso[off:off + len(raw)] == raw, f"{r['id']}: ISO/raw 불일치"
        tr = r["translation"] or ""
        # 오버라이드가 있으면 미번역(same_as_original) 행도 통과시킨다 —
        # encoded() 안의 같은 규칙과 맞춰야 한다(2026-08-30: 여기서 먼저
        # 걸러져 메모 헤더가 54사본 전부 일문으로 남았다).
        has_ov = (r["id"] in overrides) or (r["original"] in orig_overrides)
        if not has_ov and (not tr or r["same_as_original"] == "yes"):
            stats["skipped_same_or_empty"] += 1
            continue
        ko, enc = encoded(r, limit=len(raw))
        if enc is None:
            stats["kept_original_jp_or_encode"] += 1
            continue
        if len(enc) > len(raw):
            if r["subcategory"] in NO_RELOC:
                worklist.append((r["id"], r["subcategory"], len(raw), len(enc),
                                 r["original"], ko, "NOFIT_NO_RELOC"))
                stats["nofit_no_reloc"] = stats.get("nofit_no_reloc", 0) + 1
                continue
            # 제자리에는 안 들어간다. 창 마스터 포인터 테이블에 참조가 있으면
            # 아레나로 **재배치**해 길이 제한을 없앤다(§3 창 루프에서 판정).
            # 채택 실패분만 최종적으로 NOFIT 으로 보고한다.
            nofit_pool.append((off, len(raw), enc, ko, r))
            continue
        if off in seen_offsets:
            raise ValueError(f"{r['id']}: 오프셋 중복 ({seen_offsets[off]})")
        seen_offsets[off] = r["id"]
        if r["subcategory"] in NO_RELOC:
            noreloc_offs.add(off)
        inplace.append((off, len(raw), enc, r["id"], r["family"],
                        r["id"] in overrides))
        FINAL_TEXT[r["id"]] = {"path": "inplace", "ko": ko}
        stats["inplace_patched"] += 1
        if r["id"] in overrides:
            stats["override_used"] += 1

    # ---- 2.5) 미인덱스 머리 레코드 보충 (2026-08-29 게이트 2차) -------------
    # Z8 인덱스(NUL 종료 추출) 밖 레코드 중 소비자가 실증된 것만 등록한다.
    # 右左頭体他 클러스터는 ISO 전수 4곳: 0x46929/0x4A78F/0x87CC8/0x8AE61.
    # 뒤 2곳은 인덱스에 있어 패치됐고, 앞 2곳은 右 만 인덱스 밖(머리 레코드).
    # 소비자 실증: 직전 코드가 스트라이드4 즉치 베이스로 읽음
    # (0x468D4: ADC #$29/#$99 → $9929+slot*4, 0x87CA1: ADC #$C8/#$AC →
    # $ACC8+slot*4) — 제자리 동일 스트라이드 치환이라 위치 불변.
    SUPPLEMENT = [
        (0x46929, "89450000", "우", "장비창 右 머리 레코드 (base $9929)"),
        (0x87CC8, "89450000", "우", "씬 slot01 右 머리 레코드 (base $ACC8)"),
        # 로드 화면 시간 포맷 (미인덱스, ISO 전수 1곳). 時間(4B)→시간(4B),
        # 分(2B)→분(2B) 로 **길이 동일** — 제자리 치환으로 끝난다.
        (0x8AFC6, "826B253031642532648E9E8AD42530316495AA00",
         None, "로드 화면 Ｌ%01d%2d時間%01d分"),
    ]
    # 시간 포맷은 서식 토큰을 보존해야 하므로 바이트 단위로 조립한다
    _t_fmt = (bytes.fromhex("826B25303164253264")
              + strict_encode("시간", glyph_map)
              + bytes.fromhex("25303164")
              + strict_encode("분", glyph_map) + b"\x00")
    for i, (off, old_hex, ko, note) in enumerate(SUPPLEMENT):
        raw = bytes.fromhex(old_hex)
        assert iso[off:off + len(raw)] == raw, f"보충 {note}: ISO 원문 불일치"
        enc = _t_fmt if ko is None else \
            strict_encode(fullwidth(ko), glyph_map) + b"\x00"
        assert len(enc) <= len(raw), f"보충 {note}: 길이 초과"
        if off in seen_offsets:
            raise ValueError(f"보충 {note}: 오프셋 중복 ({seen_offsets[off]})")
        seen_offsets[off] = f"suppl@{off:07X}"
        inplace.append((off, len(raw), enc, f"suppl@{off:07X}",
                        "unindexed_head", False))
        stats["supplement_patched"] = stats.get("supplement_patched", 0) + 1

    # ---- 2.55) 미인덱스 이름 전 사본 치환 (2026-08-30 게이트 5차) ----------
    # 몬스터명 블록은 `u16 테이블 + 이름들` 인데 추출기가 테이블과 **첫
    # 이름**을 한 덩어리로 묶어 인덱스에서 누락시켰다(バルーン). 전투 RAM
    # 덤프(diag_battle)에서 이 블록이 렌더 소스임을 확인 — 바로 뒤 이름들이
    # 이미 한글이었다. 슬롯 내에 들어가는 한글만 **전 사본** 제자리 치환.
    UNINDEXED_NAMES = [
        ("836FD9B0DD00", "벌룬", "몬스터명 バルーン (테이블 머리에 흡수됨)"),
        # 2026-10-09 b15 게이트: 탑 전투 「モイ갑상시드出現!」= 1바이트 카타카나
        # ファミリアー 가 새 테이블로 읽힌 것. 22사본, 테이블 머리 흡수(벌룬과 동일).
        # 1바이트 코드(패·리)를 쓰면 7B 슬롯에 '패밀리어'(7B) 가 들어간다.
        ("CCA7D0D8B1B000", "패밀리어", "몬스터명 ファミリアー (테이블 머리에 흡수됨)"),
    ]
    # 다중 세그먼트(`0F` 구분) 레코드는 인덱스에 통째로 없다. 전투 결과
    # 템플릿이 여기 해당(전투 RAM 실측). 세그먼트 텍스트만 한글로 갈고
    # 제어 바이트는 원형 유지, 남는 꼬리는 00 패딩.
    #   원본: 10 魔物を倒した 0F 0D%dの経験値と 0D%dギミルを手に入れた
    #         [0F 0D%sを手に入れた] 00
    UNINDEXED_SEGMENTED = [
        ("10968295A879937C3E460F0D2564558C6F8CB1926C4F0D2564834DD0D97"
         "98EE85293FC73460F0D2573798EE85293FC734600",
         [(b"\x10", "마물격파"), (b"\x0f\x0d\x25\x64", "경험치와"),
          (b"\x0d\x25\x64", "기밀획득"), (b"\x0f\x0d\x25\x73", "획득")],
         "전투 결과(아이템 있음)"),
        ("10968295A879937C3E460F0D2564558C6F8CB1926C4F0D2564834DD0D9"
         "798EE85293FC734600",
         [(b"\x10", "마물격파"), (b"\x0f\x0d\x25\x64", "경험치와"),
          (b"\x0d\x25\x64", "기밀획득")],
         "전투 결과(아이템 없음)"),
    ]
    # 인덱스에 **아예 없는** 래퍼 UI 문자열(전투 메시지 44종). 원문 바이트
    # 전체를 키로 잡아 전 사본을 치환한다. 번역은 이 세션에서 신규 작성 —
    # 릴리스 전 인간 검토 대상(§3).
    if UNINDEXED_BATTLE.is_file():
        with UNINDEXED_BATTLE.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                raw = bytes.fromhex(row["old_hex"])
                assert raw[-2:] == b"\x0f\x00", f"{row['note']}: 래퍼 아님"
                enc = strict_encode(fullwidth(row["ko"]), glyph_map)
                body = raw[:1] + enc + b"\x0f\x00"
                assert len(body) <= len(raw), f"{row['note']}: 길이 초과"
                body += b"\x00" * (len(raw) - len(body))
                pos = 0
                while True:
                    pos = iso.find(raw, pos)
                    if pos < 0:
                        break
                    if pos not in seen_offsets:
                        seen_offsets[pos] = f"ubat@{pos:07X}"
                        inplace.append((pos, len(raw), body,
                                        f"ubat@{pos:07X}",
                                        "unindexed_battle", False))
                        stats["unindexed_battle_patched"] = \
                            stats.get("unindexed_battle_patched", 0) + 1
                    pos += 1

    for old_hex, parts, note in UNINDEXED_SEGMENTED:
        raw = bytes.fromhex(old_hex)
        body = b"".join(pre + strict_encode(fullwidth(ko), glyph_map)
                        for pre, ko in parts) + b"\x00"
        assert len(body) <= len(raw), f"{note}: 길이 초과"
        body += b"\x00" * (len(raw) - len(body))
        n = 0
        pos = 0
        while True:
            pos = iso.find(raw, pos)
            if pos < 0:
                break
            if pos not in seen_offsets:
                seen_offsets[pos] = f"useg@{pos:07X}"
                inplace.append((pos, len(raw), body, f"useg@{pos:07X}",
                                "unindexed_segmented", False))
                n += 1
            pos += 1
        stats["unindexed_seg_patched"] = \
            stats.get("unindexed_seg_patched", 0) + n
    for old_hex, ko, note in UNINDEXED_NAMES:
        raw = bytes.fromhex(old_hex)
        enc = strict_encode(fullwidth(ko), glyph_map) + b"\x00"
        if len(enc) > len(raw) and onebyte:
            enc = _enc_onebyte(fullwidth(ko)) + b"\x00"      # b15: 1바이트 코드로 재시도
        if len(enc) > len(raw):
            worklist.append((f"uname:{old_hex}", "unindexed_name", len(raw),
                             len(enc), old_hex, ko, "NOFIT"))
            continue
        body = enc + b"\x00" * (len(raw) - len(enc))
        n = 0
        pos = 0
        while True:
            pos = iso.find(raw, pos)
            if pos < 0:
                break
            if pos not in seen_offsets:
                seen_offsets[pos] = f"uname@{pos:07X}"
                inplace.append((pos, len(raw), body, f"uname@{pos:07X}",
                                "unindexed_name", False))
                n += 1
            pos += 1
        stats["unindexed_name_patched"] = \
            stats.get("unindexed_name_patched", 0) + n

    # ---- 2.6) 래퍼 미인덱스 사본 보충 (2026-08-30 게이트 4차) --------------
    # 전투 메시지 등은 씬 패키지에 `10 <내용> 0F 00` 래퍼로 한 벌 더 있고,
    # 이 사본이 **Z8 인덱스에 없다**(추출기가 래퍼 때문에 놓침). 화면에
    # 나오는 건 이쪽이라 일문으로 남았다. 내용이 인덱스 레코드의 raw 와
    # 정확히 일치할 때만 그 번역을 그대로 적용한다(fail-closed).
    by_raw = {}
    for r in rows:
        by_raw.setdefault(r["raw_hex"].upper(), r)
    wrapped = 0
    scan = 0
    while True:
        j = iso.find(b"\x0f\x00", scan)
        if j < 0:
            break
        scan = j + 2
        s = j
        while s > 0 and iso[s - 1] != 0:
            s -= 1
        if s in seen_offsets:
            continue
        # 접두 제어 바이트는 레코드마다 다르다(실측: `10` = 대사창 계열,
        # `0D` = 줄바꿈 선행). 접두 1B 있음/없음을 모두 시도하고, 내용이
        # 인덱스 레코드 raw 와 **정확히 일치**할 때만 채택한다.
        # 래퍼 사본은 원본의 **끝 제어(\p=0C, \n=0D)를 `0F` 로 대체**한
        # 변종이 있다(마법 시전 메시지 실측). 접두 유무 × 끝 제어 3종을
        # 모두 시도하고, 내용이 인덱스 레코드와 정확히 일치할 때만 채택.
        pick = None
        for k in (1, 0):
            if k and not (0x01 <= iso[s] <= 0x1F):
                continue
            for extra in (b"", b"\x0c", b"\x0d"):
                cand = by_raw.get(
                    (iso[s + k:j] + extra + b"\x00").hex().upper())
                if cand is not None:
                    pick = (k, extra, cand)
                    break
            if pick:
                break
        if pick is None:
            continue
        k, extra, src = pick
        cap = j - s - k + 1 + len(extra)    # 내용 용량(NUL 포함 환산)
        ko, enc = encoded(src, limit=cap)
        if enc is None or len(enc) > cap:
            continue
        core = enc[:-1]
        if extra and core.endswith(extra):
            core = core[:-len(extra)]      # 끝 제어는 `0F` 가 대신한다
        body = iso[s:s + k] + core + b"\x0f\x00"
        pad = ((j + 2) - s) - len(body)
        if pad < 0:
            continue
        body += b"\x00" * pad
        seen_offsets[s] = f"wrap@{s:07X}"
        inplace.append((s, (j + 2) - s, body, f"wrap@{s:07X}",
                        "wrapped_twin", False))
        wrapped += 1
    stats["wrapped_twin_patched"] = wrapped

    # 미인덱스 **재배치** 보충: 제자리에 안 들어가지만 포인터 사이트가
    # 실측 확정된 레코드. 파티/상태창 캐릭터명 フェイト 는 테이블 머리
    # 엔트리라 재패킹 런에서 빠져 있었다(1바이트 가나 4B → '페이트' 6B).
    # 포인터: sys 0x49778(=C9A6), scene 0x89900(=CADA) — 다음 엔트리가
    # +5 인 연속 배열임을 확인(2026-08-30).
    SUPPLEMENT_RELOC = [
        (0x499A6, 5, 0x49778, 0x49000, 0xC000, "페이트", "파티창 이름(sys)"),
        (0x89ADA, 5, 0x89900, 0x89000, 0xC000, "페이트", "파티창 이름(scene)"),
    ]
    for off, rl, psite, wstart_, wbase, ko, note in SUPPLEMENT_RELOC:
        logical = wbase + (off - wstart_)
        assert iso[psite:psite + 2] == bytes([logical & 0xFF, logical >> 8]), \
            f"보충 {note}: 포인터 사이트 불일치"
        assert iso[off + rl - 1] == 0, f"보충 {note}: NUL 종료 아님"
        enc = strict_encode(fullwidth(ko), glyph_map) + b"\x00"
        row = {"id": f"supplreloc@{off:07X}", "iso_offset": f"0X{off:07X}",
               "raw_length": str(rl), "original": note, "translation": ko,
               "family": "unindexed_head", "subcategory": "unindexed_head",
               "package_id": "supplement", "same_as_original": "no"}
        nofit_pool.append((off, rl, enc, ko, row))
        extra_ptr_sites.setdefault(off, []).append(psite)
        stats["supplement_reloc_queued"] = \
            stats.get("supplement_reloc_queued", 0) + 1

    # ---- 3) 전역 바이트맵 + 창 아레나 배치 ----------------------------------
    gmap: dict[int, int] = {}        # iso_off -> new byte

    def write_bytes(off, data):
        for i, bb in enumerate(data):
            gmap[off + i] = bb

    # (2026-10-11 b53) 스크립트 사이 문자열(앞 바이트가 00 이 아닌 단독 레코드 — 마을 배너 「12 91 CC 02 …」, 「02 扉が開いた！ 00 06 00 08 …」,
    # 크레딧 「01 01 06 …」 등)은 엔진이 첫 00 다음 바이트부터 명령을 이어 읽는다. 번역이 짧아 남은 칸을 00 으로 채우면 그 00 이 명령으로
    # 읽혀 스크립트가 끊긴다(쌍둥이 도시 배너 → 마을 진입 검은 화면, 사용자 게이트 b51). → 남은 칸 = 반각 공백 7E, 끝 00 은 원래 위치.
    # 포인터로 읽는 이름표(몬스터·보스 이름 — 앞 바이트가 포인터 표의 상위 바이트)는 뒤 공백이 조사 앞에 보이므로 제외.
    _row_sub = {r["id"]: r.get("subcategory", "") for r in rows}
    INLINE_PAD_SKIP = {"monster_names", "boss_names"}
    stats["inline_pad_7e"] = 0
    for off, rl, enc, rid, fam, ov in inplace:
        tail = rl - len(enc)
        if (tail > 0 and enc.endswith(b"\x00") and off > 0 and iso[off - 1] != 0
                and iso[off + rl - 1] == 0 and _row_sub.get(rid, "") not in INLINE_PAD_SKIP):
            write_bytes(off, enc[:-1] + b"\x7e" * tail + b"\x00")
            stats["inline_pad_7e"] += 1
            continue
        write_bytes(off, enc)
        write_bytes(off + len(enc), b"\x00" * (rl - len(enc)))  # 꼬리 기본 00

    # 창 = 8KB 논리 뱅크: file_window_start = run시작 - (base - (base&0xE000))
    # self 런(다중 base)은 자기 extent 전용 의사-창 — 모든 매핑에서 유효.
    windows: dict[int, dict] = {}
    for pr in pruns:
        if pr["self"]:
            continue
        wstart = pr["offs"][0] - (pr["base"] - (pr["base"] & 0xE000))
        w = windows.setdefault(wstart,
                               {"runs": [], "logical": pr["base"] & 0xE000,
                                "self": False})
        w["runs"].append(pr)
    wlist = sorted(windows.items())
    for pr in pruns:
        if pr["self"]:
            wlist.append((pr["offs"][0],
                          {"runs": [pr], "logical": None, "self": True}))

    def find_master_tables(lo, hi, logical_base, starts):
        """창 내 연속 u16 배열 중 문자열 포인터 테이블로 인정할 것.

        판정: **6엔트리 이상 연속**이 전부 창 논리범위를 가리키고, 그중
        **3개 이상이 알려진 레코드 시작**일 것. 테이블에는 Z8 인덱스 밖
        레코드(미인덱스 문자열)도 섞여 있어 '전 엔트리가 레코드 시작'을
        요구하면 배열이 끊긴다(2026-08-30 실측: 채택 1건에 그침).
        고립 u16 일치는 우연이 흔하므로(§9) 연속 길이를 근거로 쓴다."""
        known = {logical_base + (o - lo) for o in starts}
        top = logical_base + (hi - lo)
        tables = []
        i = max(0, lo - 0x2000)
        limit = min(len(iso) - 2, hi)
        while i < limit:
            v = iso[i] | (iso[i + 1] << 8)
            if logical_base <= v < top:
                j, vals = i, []
                while j < limit:
                    w_ = iso[j] | (iso[j + 1] << 8)
                    if not (logical_base <= w_ < top):
                        break
                    vals.append(w_)
                    j += 2
                if len(vals) >= 6 and sum(1 for x in vals if x in known) >= 3:
                    tables.append((i, vals))
                i = max(j, i + 2)
            else:
                i += 1
        return tables

    def has_code_immediate(lo, hi, logical):
        """LDA #lo .. LDA #hi 근접 쌍 = 코드가 주소를 즉치로 물고 있음.
        그런 레코드는 재배치/리다이렉트 금지 (테이블 밖 참조)."""
        pat = bytes([0xA9, logical & 0xFF])
        i = lo
        while True:
            i = iso.find(pat, i, hi)
            if i < 0:
                return False
            if bytes([0xA9, logical >> 8]) in iso[i:i + 12]:
                return True
            i += 1

    adopted: set[str] = set()       # 아레나로 재배치된 NOFIT 행 id
    for wstart, w in wlist:
        wend = wstart + 0x2000
        frags = [(pr["offs"][0], sum(pr["lens"])) for pr in w["runs"]]
        singles: list[dict] = []    # 이 창에서 재배치할 단독 레코드
        if not w["self"]:
            # --- 창 내 제자리 중복 dedupe (의미 손실 0) -------------------
            # 인코딩이 같은 제자리 레코드가 여럿이면 대표 1벌만 남기고,
            # 나머지는 **포인터를 대표 주소로 돌려** extent 전체를 회수한다.
            # 안전 조건: 검증된 마스터 테이블(6엔트리+ 연속)에만 참조가 있고
            # 코드 즉치 참조가 없을 것. 하나라도 어기면 그 레코드는 유지.
            wlocal = [x for x in inplace if wstart <= x[0] and x[0] + x[1] <= wend
                      and x[0] not in noreloc_offs]      # b15: 재배치 금지 행은 dedupe 도 금지
            # 테이블 엔트리는 런 행·제자리 행을 가리지 않으므로 **창 내 전
            # 레코드 시작**을 기준으로 연속성을 판정해야 배열이 끊기지 않는다.
            starts = {int(r["iso_offset"], 16) for r in targets
                      if wstart <= int(r["iso_offset"], 16) < wend}
            mtabs = find_master_tables(wstart, wend, w["logical"], starts)
            ptr_sites: dict[int, list] = {}
            for toff, vals in mtabs:
                for k, v in enumerate(vals):
                    ptr_sites.setdefault(wstart + (v - w["logical"]),
                                         []).append(toff + 2 * k)
            for _off, _sites in extra_ptr_sites.items():
                if wstart <= _off < wend:
                    ptr_sites.setdefault(_off, []).extend(_sites)
            bygroup: dict[bytes, list] = {}
            for x in wlocal:
                bygroup.setdefault(bytes(x[2]), []).append(x)
            freed = set()
            for enc_key, grp in bygroup.items():
                if len(grp) < 2:
                    continue
                grp.sort(key=lambda x: x[0])
                rep_off = grp[0][0]
                rep_log = w["logical"] + (rep_off - wstart)
                for off, rl, enc, rid, fam, ovf in grp[1:]:
                    logical = w["logical"] + (off - wstart)
                    sites = ptr_sites.get(off, [])
                    if not sites or has_code_immediate(wstart, wend, logical):
                        continue
                    for s in sites:
                        write_bytes(s, rep_log.to_bytes(2, "little"))
                    frags.append((off, rl))
                    freed.add(off)
                    stats["dedupe_inplace_freed"] = \
                        stats.get("dedupe_inplace_freed", 0) + rl
            # --- NOFIT 재배치 (2026-08-30): 제자리에 안 들어가는 레코드도
            # 검증된 마스터 테이블 참조가 있으면 아레나로 옮긴다. extent 가
            # 용량에 들어오고 인코딩이 수요에 들어오므로 순비용 = 초과분뿐.
            # (메인 메뉴 魔法/状態…·도구 명령 使う/交換/捨てる·メモ 등)
            for off, rl, enc, ko, r in nofit_pool:
                if not (wstart <= off and off + rl <= wend):
                    continue
                logical = w["logical"] + (off - wstart)
                sites = ptr_sites.get(off, [])
                if not sites or has_code_immediate(wstart, wend, logical):
                    continue
                singles.append({"off": off, "rl": rl, "enc": enc, "ko": ko,
                                "row": r, "sites": sites, "window": wstart})
            # 순비용(초과분) 오름차순 — 배치가 안 되면 뒤(비싼 것)부터 뺀다
            singles.sort(key=lambda sg: len(sg["enc"]) - sg["rl"])
            for off, rl, enc, rid, fam, ovf in inplace:
                if off in freed or off in noreloc_offs:   # b15: 재배치 금지 행 꼬리는 도너로 안 쓴다
                    continue
                if wstart <= off and off + rl <= wend and rl - len(enc) >= 4:
                    frags.append((off + len(enc), rl - len(enc)))
                    stats["donor_tail_bytes"] += rl - len(enc)
        base_frags = sorted(frags)

        def build_window(use_singles):
            """(items, frags) 구성. `use_singles` 면 NOFIT 재배치분의 extent 를
            용량에, 인코딩을 수요에 넣는다 — 순비용은 초과분뿐이다.
            창 내 dedupe: 인코딩이 같은 레코드는 **한 벌만 배치**하고 주소를
            공유한다(아레나 행은 어차피 포인터가 재작성되므로 무위험)."""
            uniq: dict[bytes, list] = {}
            for pr in w["runs"]:
                for r, enc in zip(pr["rows"], pr["encs"]):
                    uniq.setdefault(bytes(enc), []).append((pr, r))
            if use_singles:
                for sg in singles:
                    uniq.setdefault(bytes(sg["enc"]), []).append(
                        ({"sub": sg["row"]["subcategory"], "single": sg},
                         sg["row"]))
            its = [(len(e), e, holders) for e, holders in uniq.items()]
            its.sort(key=lambda x: (-x[0], x[2][0][1]["id"]))
            fr = base_frags + ([(sg["off"], sg["rl"]) for sg in singles]
                               if use_singles else [])
            return its, sorted(fr), sum(len(e) * (len(h) - 1)
                                        for e, h in uniq.items())

        items, frags, dup_saved = build_window(bool(singles))
        # 프래그먼트별 subset-sum DP (bin completion): 각 조각을 남은 항목의
        # 부분집합 중 가장 꽉 차는 조합으로 채운다 — 슬리버 분산으로 작은
        # 항목이 못 들어가는 문제를 없앤다.
        def run_placement(forced_idx):
            """조각을 큰 순서로 채운다. `forced_idx` 는 직전 시도에서 좌초한
            항목 — 큰 조각 앞머리에 **강제 배치**한 뒤 나머지를 subset-sum
            으로 채운다. 마지막에 조각별 잔여를 first-fit 으로 회수한다."""
            placed: dict[str, int] = {}
            leftovers: list[list[int]] = []
            remset = set(range(len(items)))
            forced_left = list(forced_idx)
            for fo, fsz in sorted(frags, key=lambda f: -f[1]):
                if not remset:
                    break
                cur, avail = fo, fsz
                nxt = []
                for i in forced_left:
                    ln = items[i][0]
                    if i in remset and ln <= avail:
                        for _pr, r in items[i][2]:
                            placed[r["id"]] = cur
                        cur += ln
                        avail -= ln
                        remset.discard(i)
                    else:
                        nxt.append(i)
                forced_left = nxt
                idxs = sorted(remset)
                reach = {0: -1}      # 합 -> (마지막 항목 위치, 이전 합)
                back = {}
                for pos, i in enumerate(idxs):
                    ln = items[i][0]
                    for s in sorted(reach, reverse=True):
                        ns = s + ln
                        if ns <= avail and ns not in reach:
                            reach[ns] = pos
                            back[ns] = s
                chosen = set()
                s = max(reach)
                while s > 0:
                    chosen.add(idxs[reach[s]])
                    s = back[s]
                for i in sorted(chosen):
                    ln = items[i][0]
                    for _pr, r in items[i][2]:   # 중복 전원이 주소 공유
                        placed[r["id"]] = cur
                    cur += ln
                    remset.discard(i)
                leftovers.append([cur, fo + fsz - cur])
            if remset:
                leftovers.sort(key=lambda f: -f[1])
                for i in sorted(remset):
                    ln = items[i][0]
                    for frag in leftovers:
                        if frag[1] >= ln:
                            for _pr, r in items[i][2]:
                                placed[r["id"]] = frag[0]
                            frag[0] += ln
                            frag[1] -= ln
                            remset.discard(i)
                            break
            return placed, sorted(remset)

        def run_fit(best_fit: bool):
            """FFD/BFD: 큰 항목부터 조각에 넣는다. subset-sum 이 조각마다
            잔여를 잘게 남겨 큰 항목이 좌초할 때의 대안 전략."""
            caps = [[fo, fsz] for fo, fsz in frags]
            placed: dict[str, int] = {}
            unplaced = []
            for i in sorted(range(len(items)), key=lambda k: -items[k][0]):
                ln = items[i][0]
                cands = [c for c in caps if c[1] >= ln]
                if not cands:
                    unplaced.append(i)
                    continue
                c = min(cands, key=lambda c: c[1]) if best_fit else cands[0]
                for _pr, r in items[i][2]:
                    placed[r["id"]] = c[0]
                c[0] += ln
                c[1] -= ln
            return placed, unplaced

        # 전략 다중 시도: 하나라도 전량 배치에 성공하면 그걸 쓴다.
        # (2026-08-29 실측: 창 여유 10B 인데 7B 항목이 슬리버 분산으로
        #  좌초 → fail-closed 로 창 전체가 일문 복귀하는 사고 방지)
        def attempt():
            forced_idx: list[int] = []
            placed, rem = run_placement(forced_idx)
            for _ in range(5):
                if not rem:
                    break
                forced_idx = rem + [i for i in forced_idx if i not in rem]
                placed, rem = run_placement(forced_idx)
            if rem:
                for bf in (True, False):
                    p2, u2 = run_fit(bf)
                    if not u2:
                        stats["placement_fallback"] = \
                            stats.get("placement_fallback", 0) + 1
                        return p2, []
            return placed, rem

        placed_addr, rem_idx = attempt()
        # NOFIT 재배치가 배치를 깨뜨리면 **비싼 것부터 하나씩 뺀다** — 전부
        # 포기하면 멀쩡히 들어갈 행까지 일문으로 남는다. 창 전체
        # fail-closed(일문 복귀)보다는 재배치 축소가 항상 낫다.
        # b14 (2026-10-09): 창이 넘치면 **축약 대안이 있는 행만, 절약이 큰 순서로
        # 하나씩** 축약으로 바꿔 재시도한다(최소 축약 — 나머지는 전체 표기 유지).
        # 사용자 요구: "축약하면 의미가 흐려지는 이름이 많다. 원문 길이를 최대한 유지".
        # 창 전체 need ≤ capacity 만 맞추면 포인터 재작성으로 전량 재배치된다.
        def short_candidates():
            cands = []
            for pr in w["runs"]:
                for k, (r, enc) in enumerate(zip(pr["rows"], pr["encs"])):
                    if r["id"] in shortened_ids:
                        continue
                    _ko_s, enc_s = encoded(r, limit=0)
                    if enc_s is not None and len(enc_s) < len(enc):
                        cands.append((len(enc) - len(enc_s), pr, k, r, enc_s, _ko_s))
            cands.sort(key=lambda c: (-c[0], c[3]["id"]))
            return cands
        shortened_ids: set[str] = set()
        while rem_idx:
            need = sum(ln for ln, _, _ in items)
            cap = sum(sz for _, sz in frags)
            cands = short_candidates()
            if need > cap and cands:
                sav, pr, k, r, enc_s, ko_s = cands[0]
                pr["encs"][k] = enc_s
                shortened_ids.add(r["id"])
                stats.setdefault("min_short_applied", []).append(
                    {"window": f"{wstart:07X}", "id": r["id"],
                     "original": r["original"], "short": ko_s, "saved": sav})
                items, frags, dup_saved = build_window(bool(singles))
                placed_addr, rem_idx = attempt()
                continue
            if singles:
                singles = singles[:-1]      # deficit 오름차순 정렬 → 비싼 것 제거
                items, frags, dup_saved = build_window(bool(singles))
                placed_addr, rem_idx = attempt()
                stats["nofit_reloc_declined"] = \
                    stats.get("nofit_reloc_declined", 0) + 1
                continue
            break
        stats["dedupe_saved_bytes"] = stats.get("dedupe_saved_bytes", 0) \
            + dup_saved
        stats.setdefault("window_report", []).append(
            {"window": f"{wstart:07X}", "runs": len(w["runs"]),
             "capacity": sum(sz for _, sz in frags),
             "need": sum(ln for ln, _, _ in items),
             "deficit": max(0, sum(ln for ln, _, _ in items)
                            - sum(sz for _, sz in frags))})
        remaining = [items[i] for i in rem_idx]
        overflow = [(holders[0][1]["id"], holders[0][0]["sub"], ln,
                     holders[0][1]["original"])
                    for ln, enc, holders in remaining]
        if overflow:
            # fail-closed: 이 창의 **재배치**는 포기 (부분 재배치 = 포인터 정합 붕괴).
            # b14 (2026-10-09): 단, 포인터를 건드리지 않는 **같은 길이 제자리 치환**은
            # 정합과 무관하므로 창을 통째로 버리지 않고 맞는 행만 제자리에 쓴다
            # (2882 몬스터명 블록: 창 부족 10B 때문에 7B 에 맞는 고블린까지 일문으로
            # 남던 문제). 안 맞는 행만 worklist 로.
            for rid, sub, ln, orig in overflow:
                worklist.append((rid, sub, ln, -1, orig, "",
                                 "ARENA_OVERFLOW"))
                stats["arena_overflow_rows"] += 1
            for pr in w["runs"]:
                n_fit = 0
                for r, enc in zip(pr["rows"], pr["encs"]):
                    off, rl = int(r["iso_offset"], 16), int(r["raw_length"])
                    if len(enc) > rl:
                        _k2, e2 = encoded(r, limit=rl)      # 전체 표기가 안 들어가면 축약 폴백
                        if e2 is not None and len(e2) <= rl:
                            enc = e2
                    if len(enc) <= rl:
                        write_bytes(off, enc)
                        write_bytes(off + len(enc), b"\x00" * (rl - len(enc)))
                        n_fit += 1
                    else:
                        worklist.append((r["id"], sub, rl, len(enc),
                                         r["original"], ko_of(r), "NOFIT_IN_SKIPPED_WINDOW"))
                stats["skipped_window_inplace_fit"] =                     stats.get("skipped_window_inplace_fit", 0) + n_fit
                worklist.append((f"RUN:{pr['pkg']}:{pr['sub']}"
                                 f"@{pr['offs'][0]:07X}", pr["sub"],
                                 sum(pr["lens"]), -1,
                                 f"{len(pr['rows'])} rows, inplace_fit={n_fit}", "",
                                 "WINDOW_SKIPPED"))
            continue
        stats["arena_windows"] += 1
        for pr in w["runs"]:
            write_bytes(pr["offs"][0], b"\x00" * sum(pr["lens"]))
        for sg in singles:                      # 재배치 단독 레코드 extent
            write_bytes(sg["off"], b"\x00" * sg["rl"])
        for pr in w["runs"]:
            for r, enc in zip(pr["rows"], pr["encs"]):
                write_bytes(placed_addr[r["id"]], enc)
        for sg in singles:
            addr = placed_addr[sg["row"]["id"]]
            write_bytes(addr, sg["enc"])
            newv = w["logical"] + (addr - wstart)
            for site in sg["sites"]:            # 마스터 테이블 포인터 재작성
                write_bytes(site, newv.to_bytes(2, "little"))
            adopted.add(sg["row"]["id"])
            FINAL_TEXT[sg["row"]["id"]] = {"path": "reloc", "ko": sg.get("ko", FINAL_TEXT.get(sg["row"]["id"], {}).get("ko", ""))}
            stats["nofit_relocated"] = stats.get("nofit_relocated", 0) + 1
        for pr in w["runs"]:
            for toff, t_base in pr["prim"]:
                # 테이블별 base — self 런은 배치가 자기 extent 안이라
                # 어느 매핑에서든 t_base + (새오프셋-런시작) 이 성립
                if w["self"]:
                    newv = {o: t_base + (placed_addr[r["id"]] - pr["offs"][0])
                            for r, o in zip(pr["rows"], pr["offs"])}
                else:
                    newv = {o: w["logical"] + (placed_addr[r["id"]] - wstart)
                            for r, o in zip(pr["rows"], pr["offs"])}
                write_bytes(toff, b"".join(
                    newv[o].to_bytes(2, "little") for o in pr["offs"]))
            old2new = {}
            for r, o in zip(pr["rows"], pr["offs"]):
                oldv = pr["base"] + (o - pr["offs"][0])
                if w["self"]:
                    old2new[oldv] = pr["base"] + \
                        (placed_addr[r["id"]] - pr["offs"][0])
                else:
                    old2new[oldv] = w["logical"] + \
                        (placed_addr[r["id"]] - wstart)
            for toff, vals in pr["extra"]:
                write_bytes(toff, b"".join(old2new[v].to_bytes(2, "little")
                                           for v in vals))
                stats["extra_tables_rewritten"] += 1
            stats["arena_runs"] += 1
            stats["arena_rows"] += len(pr["rows"])
            for r in pr["rows"]:
                if r["id"] in overrides:
                    stats["override_used"] += 1

    # ---- 3.9) 재배치에 실패한 NOFIT 행만 최종 보고 -------------------------
    for off, rl, enc, ko, r in nofit_pool:
        if r["id"] in adopted:
            continue
        stats["kept_original_nofit"] += 1
        worklist.append((r["id"], r["family"], rl, len(enc),
                         r["original"], ko, "NOFIT"))

    # ---- 4) gmap → 연속 span 패치 (원본과 같은 바이트는 제외) ---------------
    changed = sorted(k for k, v in gmap.items() if iso[k] != v)
    i = 0
    while i < len(changed):
        j = i
        while j + 1 < len(changed) and changed[j + 1] <= changed[j] + 8:
            j += 1
        s, e = changed[i], changed[j] + 1
        new = bytes(gmap.get(k, iso[k]) for k in range(s, e))
        patches.append({"iso_off": s,
                        "old_hex": iso[s:e].hex().upper(),
                        "new_hex": new.hex().upper(),
                        "id": f"edit@{s:07X}", "mode": "bytes"})
        i = j + 1

    # 패치 간 겹침 검사
    spans = sorted((p["iso_off"], p["iso_off"] + len(p["old_hex"]) // 2)
                   for p in patches)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        if e1 > s2:
            raise ValueError(f"패치 겹침 @{s1:07X}")

    OUT_PATCHES.write_text(json.dumps(
        {"format": "BTRACK-B10-MENU-PATCHES", "stats": stats,
         "review": "번역 출처 = Z8 entry index (Switch판 최종 번역 계열). "
                   "overrides 의 짧춤 초안은 인간 검토 필수.",
         "patches": patches}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _rows_by_id = {r["id"]: r for r in targets}
    OUT_FINAL_TEXT.write_text(json.dumps(
        {k: {**v, "original": _rows_by_id.get(k, {}).get("original", ""),
             "translation": _rows_by_id.get(k, {}).get("translation", ""),
             "category": _rows_by_id.get(k, {}).get("category", ""),
             "subcategory": _rows_by_id.get(k, {}).get("subcategory", "")}
         for k, v in FINAL_TEXT.items()}, ensure_ascii=False, indent=0), encoding="utf-8")
    with OUT_WORKLIST.open("w", encoding="utf-8", newline="") as f:
        f.write("id\tfamily\traw_len\tneed_len\toriginal\ttranslation\treason\n")
        for row in worklist:
            f.write("\t".join(str(x) for x in row) + "\n")
    print(json.dumps({"status": "OK", "stats": stats,
                      "worklist_rows": len(worklist)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
