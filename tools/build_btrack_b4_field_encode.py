#!/usr/bin/env python3
"""B트랙 B4 — field 235 레코드의 한국어를 스트림 바이트로 인코딩.

바이트 문법 (2026-08-22 raw 대조 확정):
  {#x}  -> 0x23, ASCII(x)          {%x}p -> 0x25, ASCII(x), 파라미터 1바이트
  \\n   -> 0x0D                    \\p   -> 0x0C
  한글  -> btrack_slot_assignment SJIS 2바이트
  기타 표시 문자 -> NFKC 전각화 후 shift_jis 2바이트 (공백=8140)
  가나(폴백 텍스트 한정) -> 1바이트 토큰(KANA) 또는 SJIS 2바이트
  종결  -> 0x00

파라미터 바이트: ASCII 문자면 ord(그 문자), 히라가나면 KANA 토큰
(Switch 표기 '%f0'과 master 표기 '{%f}ぉ' 모두 수용 — 동일 바이트 0x30).

줄바꿈 규격 (구조분석 §11.3): 한 줄 전각 24자 한도(권장 20), 창당 3줄.
화자 페이지는 화자줄 + 본문 2줄, 무화자 페이지는 본문 3줄. 초과분은 \\p 로
새 페이지(무화자)로 넘긴다.

출력: translation/btrack_b4_field_payload.json (+ 요약 manifest)
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDX = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
B3 = ROOT / "translation" / "btrack_b3_translation_map.tsv"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"

OUT_PAYLOAD = ROOT / "translation" / "btrack_b4_field_payload.json"
OUT_MANIFEST = ROOT / "translation" / "btrack_b4_manifest.json"

BS = chr(92)
BSN = BS + "n"
BSP = BS + "p"

# Z8.6 경계 보정 ID -> master ID
CORRECTED_TO_MASTER = {
    "iso:010CABD": "iso:010CAE1",
    "iso:010D036": "iso:010D080",
    "iso:011F01E": "iso:011F011",
}
# 위 3건은 master 가 원문의 뒷부분(부분 문자열)만 담고 있어 번역이 잘려 있었다 — 원문 전체 번역으로 대체, 줄바꿈 그대로(재줄바꿈 안 함).
# (2026-10-11 게이트: 「Ⅱ 버튼」 누락 신고 → 같은 원인 3건 일괄)
CORRECTED_KO = {
    # とおせんぼするようなやな人は／行きたい方向のキーを押しながらⅡボタンを押すと／すり抜けられるわよ
    "iso:010CABD": BS.join(["길을 막고 안 비켜 주는 심술궂은 사람은", "n가고 싶은 방향의 키를 누르면서", "nⅡ 버튼을 누르면 빠져나갈 수 있어"]),
    # オートバトルはとっても便利だけど／うまく付き合わないと／思わぬ被害を受けるわよ ⏎ オートバトルから抜けるには／戦闘中、Ⅱボタンを押し続けてね／フェイトたちのターンが来たら解除されるわ
    "iso:010D036": BS.join(["오토 배틀은 정말 편리하지만", "n잘 다루지 못하면", "n뜻밖의 피해를 입을 수 있어", "p오토 배틀을 풀려면",
                            "n전투 중에 Ⅱ 버튼을 계속 누르고 있어", "n페이트 일행의 차례가 오면 해제될 거야"]),
    # 次の目的のこと (선택지 — master 에 포인터 바이트가 섞여 일본어 그대로 나갔다)
    "iso:011F01E": "다음 목적에 대해",
}

LINE_MAX = 24          # 하드 한도 (전각)
LINE_PREF = 20         # 우선 목표
BODY_LINES_WITH_SPEAKER = 2
BODY_LINES_NO_SPEAKER = 3

# 사용 가능 저장 예산 (A-2 canary PASS 로 확정된 RAM 목적지)
BUDGET = {"bank_7A_7B": 16384, "bank_7E": 8192, "bank_6D_head": 4096}
INDEX_RESERVE = 32 + 235 * 12   # Z8.7 wire 형식 유지 가정

KANA = {}
for base, text in (
    (0x28, "ぁあぃいぅうぇえぉお"), (0x32, "かがきぎくぐけげこご"),
    (0x3C, "さざしじすずせぜそぞ"), (0x46, "ただちぢっつづてでとど"),
    (0x51, "なにぬねの"), (0x56, "はばぱひびぴふぶぷへべぺほぼぽ"),
    (0x65, "まみむめも"), (0x6A, "ゃやゅゆょよ"),
    (0x70, "らりるれろ"), (0x75, "ゎわゐゑをん"),
):
    for i, ch in enumerate(text):
        KANA[ch] = base + i

CTRL_RE = re.compile(r"(\{#[0-9A-Fa-f]{1,2}\}|\{%[0-9A-Za-z]\}.|\{~\}|\{0B\})")   # {0B} = 키 대기(▽) 제어 0x0B (2026-10-13 — 종전엔 ｛０Ｂ｝ 글자로 찍힘)   # {~} = 반칸(0x7E, 2026-10-10)


# ---- 표시 폭 (전각 셀 수) ----------------------------------------------------

def cells(text: str) -> int:
    return len(CTRL_RE.sub("", text))


# ---- 한국어 재줄바꿈 ---------------------------------------------------------

BRACKET_KEEP = 20   # (2026-10-13 사용자 제보 「시간의 / 강정」) 이 셀 수 이하의 「…」『…』 는 한 단위로 — 이름이 줄에서 잘리지 않게. 긴 인용문은 종전대로


def keep_brackets(words: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(words):
        w = words[i]
        depth = sum(w.count(c) for c in "「『") - sum(w.count(c) for c in "」』")
        if depth > 0:
            j, d, unit = i, depth, w
            while d > 0 and j + 1 < len(words):
                j += 1
                unit += " " + words[j]
                d += sum(words[j].count(c) for c in "「『") - sum(words[j].count(c) for c in "」』")
            lo = min(unit.find(c) for c in "「『" if c in unit)
            hi = max(unit.rfind(c) for c in "」』")
            if d <= 0 and cells(unit[lo:hi + 1]) <= BRACKET_KEEP and cells(unit) <= LINE_MAX:   # 괄호 안만 잼(뒤 조사 제외)
                out.append(unit)
                i = j + 1
                continue
        out.append(w)
        i += 1
    return out


def wrap_line(text: str, limit: int) -> list[str]:
    """공백 우선 줄바꿈. limit 전각 셀."""
    words = keep_brackets(text.split(" "))
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip(" ") if cur else w   # 반각 공백만 — 전각 들여쓰기 유지({0B} 그림 페이지)
        if cells(cand) <= limit:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        # 단어 자체가 한도 초과면 강제 분할
        while cells(w) > limit:
            lines.append(w[:limit])
            w = w[limit:]
        cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def repaginate(ko: str) -> str:
    """B3 ko(master 표기)를 24자/3줄 규격으로 재구성."""
    out_pages = []
    for page in ko.split(BSP):
        # 페이지 선두 {%x}p / {#x} 프리픽스 유지
        m = re.match(r"^((?:\{%[0-9A-Za-z]\}.|\{#[0-9A-Fa-f]{1,2}\})*)", page)
        prefix = m.group(1)
        rest = page[len(prefix):]
        # 화자줄 감지: SPEAKER：\n{#1}
        speaker = None
        sm = re.match(r"^([^\\{}]{1,12}[：:])" + re.escape(BSN) + r"\{#1\}", rest)
        if sm:
            speaker = sm.group(1)
            body = rest[sm.end():]
        else:
            body = rest
        # (2026-10-13) {0B}(키 대기) 가 있는 페이지 = 원본이 3줄을 넘겨 스크롤하는 페이지(편지·지도 그림) — 번역 줄바꿈과 대기 위치를 그대로 두고
        # 24칸 넘는 줄만 그 줄 안에서 접는다(줄 합치기·3줄 분할 금지 — 합치면 대기 위치가 어긋나고 그림이 무너진다)
        if "{0B}" in body:
            lines = []
            for seg in body.split(BSN):
                lines += wrap_line(seg.strip(" "), LINE_MAX) if seg.strip(" ") else [""]
            page_txt = prefix + (speaker + BSN + "{#1}" if speaker else "") + BSN.join(lines)
            out_pages.append(page_txt)
            continue
        # 본문: 기존 줄바꿈 해제 후 재줄바꿈
        body_text = " ".join(
            seg for seg in body.split(BSN)) if body else ""
        body_text = re.sub(r"\s+", " ", body_text).strip()
        lines = wrap_line(body_text, LINE_MAX) if body_text else []
        # 창 분배
        cap = BODY_LINES_WITH_SPEAKER if speaker else BODY_LINES_NO_SPEAKER
        first, restl = lines[:cap], lines[cap:]
        page_txt = prefix
        if speaker:
            page_txt += speaker + BSN + "{#1}"
        page_txt += BSN.join(first)
        out_pages.append(page_txt)
        while restl:
            chunk, restl = restl[:BODY_LINES_NO_SPEAKER], restl[BODY_LINES_NO_SPEAKER:]
            out_pages.append(BSN.join(chunk))
    return BSP.join(out_pages)


# ---- 바이트 인코딩 -----------------------------------------------------------

class EncodeError(Exception):
    pass


def encode_stream(text: str, slot_sjis: dict[str, bytes]) -> bytes:
    out = bytearray()
    i = 0
    while i < len(text):
        m = CTRL_RE.match(text, i)
        if m:
            tok = m.group(0)
            if tok == "{~}":           # 반칸 제어(0x7E) — 마스터 표기의 {~} 토큰. 종전엔 ｛～｝ 글자로 나갔다.
                out.append(0x7E)
                i = m.end()
                continue
            if tok == "{0B}":          # 키 대기(▽) 제어 — 원본 바이트 그대로(편지·지도 등 스크롤 페이지)
                out.append(0x0B)
                i = m.end()
                continue
            if tok.startswith("{#"):
                out.append(0x23)
                out.extend(tok[2:-1].encode("ascii"))
            else:                      # {%x}p
                out.append(0x25)
                out.append(ord(tok[2]))
                p = tok[-1]
                if p in KANA:
                    out.append(KANA[p])
                elif ord(p) < 0x80:
                    out.append(ord(p))
                else:
                    raise EncodeError(f"인코딩 불가 파라미터: {p!r}")
            i = m.end()
            continue
        if text.startswith(BSN, i):
            out.append(0x0D)
            i += 2
            continue
        if text.startswith(BSP, i):
            out.append(0x0C)
            i += 2
            continue
        ch = text[i]
        i += 1
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            code = slot_sjis.get(ch)
            if code is None:
                raise EncodeError(f"미배정 한글: {ch}")
            out.extend(code)
            continue
        if ch == " ":
            out.extend(b"\x81\x40")
            continue
        if ch in KANA:                 # 폴백 텍스트의 히라가나
            out.append(KANA[ch])
            continue
        # ASCII 인용부호 → SJIS 전각 직결 (승격 불가 문자, 슬롯 미배정 실측)
        if ch == "'":
            out.extend(b"\x81\x66")            # ’ (0x8166)
            continue
        if ch == '"':
            out.extend(b"\x81\x68")            # ” (0x8168)
            continue
        # 승격 경로가 못 다루는 심볼 → SJIS 직결 (2026-08-23 전 씬 인코드에서
        # 발견: '~' 는 U+FF5E 가 shift_jis 코덱에 없어 승격 실패(wave dash),
        # '·' 는 SJIS 매핑 부재). 0x8160/0x8145 미배정은 슬롯 감사로 확인.
        if ch == "~":
            out.extend(b"\x81\x60")            # ～ (0x8160)
            continue
        if ch == "Ⅱ":                          # NEC 특수문자 Ⅱ (0x8755, 원문 「Ⅱボタン」) — NFKC 가 'II' 로 풀면 1바이트가 된다
            out.extend(b"\x87\x55")
            continue
        if ch == "·":
            out.extend(b"\x81\x45")            # ・ (0x8145)
            continue
        # NFKC 이전에 원문자 2바이트 SJIS 직행 시도 — '…'(U+2026) 를 NFKC 가
        # '...' 3문자로 분해해 ASCII 2E 폴백(카드 교체 슬롯과 충돌, ㅊㅊㅊ 렌더)
        # 시키는 결함 수정 (2026-08-23 b6 게이트 발견). 0x8163 미배정 실측 확인.
        try:
            enc0 = ch.encode("shift_jis")
            if len(enc0) == 2:
                out.extend(enc0)
                continue
        except UnicodeEncodeError:
            pass
        full = unicodedata.normalize("NFKC", ch)
        full = {"“": "「", "”": "」", "‘": "「", "’": "」"}.get(full, full)
        try:
            enc = full.encode("shift_jis")
        except UnicodeEncodeError:
            raise EncodeError(f"인코딩 불가 문자: {ch!r}")
        if len(enc) == 1:              # ASCII → 전각으로 승격
            wide = unicodedata.normalize("NFKC", chr(0xFF00 + ord(full) - 0x20)) \
                if 0x21 <= ord(full) <= 0x7E else None
            enc2 = None
            if wide:
                try:
                    enc2 = chr(0xFF00 + ord(full) - 0x20).encode("shift_jis")
                except UnicodeEncodeError:
                    enc2 = None
            if enc2 and len(enc2) == 2:
                out.extend(enc2)
            else:
                raise EncodeError(f"1바이트 문자 잔존: {ch!r}")
        else:
            out.extend(enc)
    out.append(0x00)
    return bytes(out)


def main() -> None:
    assign = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    slot_sjis = {ch: bytes.fromhex(e["sjis"]) for ch, e in assign.items()}
    b3 = {r["id"]: r for r in csv.DictReader(
        B3.open(encoding="utf-8", newline=""), delimiter="\t")}
    idx = list(csv.DictReader(IDX.open(encoding="utf-8", newline=""), delimiter="\t"))

    records = []
    errors = []
    total = 0
    line_over = 0
    for e in idx:
        rid = e["id"]
        mid = CORRECTED_TO_MASTER.get(rid, rid)
        b = b3.get(mid)
        if b is None:
            errors.append((rid, "B3 맵에 없음"))
            continue
        ko = CORRECTED_KO[rid] if rid in CORRECTED_KO else repaginate(b["ko"])
        for page in ko.split(BSP):
            for ln in page.split(BSN):
                if cells(ln) > LINE_MAX:
                    line_over += 1
        try:
            data = encode_stream(ko, slot_sjis)
        except EncodeError as ex:
            errors.append((rid, str(ex)))
            continue
        total += len(data)
        records.append({
            "id": rid, "master_id": mid, "b3_status": b["status"],
            "source_key_u24le": e["source_key_u24le"],
            "original_raw_length": int(e["raw_length"]),
            "ko_repaginated": ko,
            "encoded_hex": data.hex().upper(),
            "encoded_length": len(data),
        })

    budget_total = sum(BUDGET.values())
    fit = INDEX_RESERVE + total <= budget_total
    manifest = {
        "format": "BTRACK-B4-FIELD-PAYLOAD",
        "records": len(records),
        "errors": errors,
        "line_over_24": line_over,
        "text_bytes_total": total,
        "index_reserve": INDEX_RESERVE,
        "budget": BUDGET,
        "budget_total": budget_total,
        "fit": fit,
        "headroom": budget_total - INDEX_RESERVE - total,
        "wrap_policy": {"line_max": LINE_MAX, "line_pref": LINE_PREF,
                        "speaker_page_body_lines": BODY_LINES_WITH_SPEAKER,
                        "plain_page_body_lines": BODY_LINES_NO_SPEAKER},
    }
    OUT_PAYLOAD.write_text(json.dumps(
        {"manifest": manifest, "records": records}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    manifest["payload_sha256"] = hashlib.sha256(OUT_PAYLOAD.read_bytes()).hexdigest()
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in
                      ("records", "text_bytes_total", "index_reserve",
                       "budget_total", "fit", "headroom", "line_over_24")},
                     ensure_ascii=False, indent=1))
    if errors:
        print("오류", len(errors), "건:")
        for rid, msg in errors[:10]:
            print("  ", rid, msg)


if __name__ == "__main__":
    main()
