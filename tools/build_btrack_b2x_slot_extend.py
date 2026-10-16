#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B2x — 슬롯 배정 증분 확장 (기존 배정 불변).

b2 재실행은 빈도순 전면 재배정이라 금지 (기존 페이로드·카드 전부 무효화).
이 도구는 새 한글 문자를 **남은 여유 슬롯**에만 추가한다:
  - 기존 assignment 의 어떤 항목도 변경하지 않는다 (fail-closed 검증).
  - 슬롯 선정 규칙은 b2 §배정 규칙과 동일 (카드 UI 한자 제외, 게임 미사용
    한자 우선, 그다음 저빈도·슬롯 오름차순).
  - 카드는 원본을 덮지 않고 새 파일로: SystemCard3_btrack_full_v2.pce
    (b10 계열의 CARD_SRC — b9 이하는 기존 btrack_full 을 계속 참조).

사용: python tools/build_btrack_b2x_slot_extend.py <추가할 문자들...>
예:   python tools/build_btrack_b2x_slot_extend.py 겟렛뷰샥
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b2_slot_assignment import (
    BIOS_SRC, EXPECTED_BIOS_SHA1, FONT_BASE, GLYPH_BYTES,
    KANJI_SLOT_MIN, KANJI_SLOT_MAX, CARD_UI_KANJI,
    load_font_sheet, render_hangul, game_kanji_usage,
)
from analyze_system_card_font_slots import glyph_index

ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
CARD_SRC = ROOT / "probes" / "SystemCard3_btrack_full.pce"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_full_v2.pce"


def main() -> None:
    chars = []
    for arg in sys.argv[1:]:
        chars.extend(arg)
    if not chars:
        raise SystemExit("사용: build_btrack_b2x_slot_extend.py <문자들>")

    doc = json.loads(ASSIGN.read_text(encoding="utf-8"))
    assignment = doc["assignment"]
    before = json.dumps(assignment, ensure_ascii=False, sort_keys=True)
    new_chars = [c for c in chars if c not in assignment]
    for c in new_chars:
        assert "가" <= c <= "힣", f"한글 아님: {c}"

    bios = bytearray(BIOS_SRC.read_bytes()[512:])
    if hashlib.sha1(bytes(bios)).hexdigest() != EXPECTED_BIOS_SHA1:
        raise ValueError("시스템카드 SHA-1 불일치")
    card = bytearray(CARD_SRC.read_bytes())
    assert len(card) == 256 * 1024

    # b2 와 동일한 슬롯 인벤토리
    slot_info = {}
    for lead in list(range(0x88, 0xA0)) + list(range(0xE0, 0xF0)):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            code = bytes((lead, trail))
            idx = glyph_index(code, bytes(bios))
            if idx is None or not (KANJI_SLOT_MIN <= idx <= KANJI_SLOT_MAX):
                continue
            if idx in slot_info:
                continue
            try:
                kanji = code.decode("shift_jis")
            except UnicodeDecodeError:
                continue
            slot = bios[FONT_BASE + idx * GLYPH_BYTES:
                        FONT_BASE + (idx + 1) * GLYPH_BYTES]
            if all(b in (0x00, 0xFF) for b in slot):
                continue
            slot_info[idx] = (code, kanji)
    for ch in CARD_UI_KANJI:
        slot_info.pop(glyph_index(ch.encode("shift_jis"), bytes(bios)), None)
    used_idx = {e["glyph_index"] for e in assignment.values()}
    free = {i: v for i, v in slot_info.items() if i not in used_idx}
    if len(new_chars) > len(free):
        raise SystemExit(f"FAIL: 신규 {len(new_chars)}자 > 여유 {len(free)}")

    usage = game_kanji_usage()
    order = sorted(free.items(), key=lambda kv: (usage.get(kv[1][1], 0), kv[0]))
    im = load_font_sheet()
    added = {}
    for ch, (idx, (code, kanji)) in zip(new_chars, order):
        glyph = render_hangul(im, ch)
        off = FONT_BASE + idx * GLYPH_BYTES
        card[off:off + GLYPH_BYTES] = glyph
        assignment[ch] = {
            "sjis": code.hex().upper(), "glyph_index": idx,
            "original_kanji": kanji, "kanji_game_freq": usage.get(kanji, 0),
            "ko_freq": 0, "b2x_added": True,
        }
        added[ch] = {"sjis": code.hex().upper(), "slot": idx, "kanji": kanji}

    # 기존 배정 불변 검증
    after_existing = {k: v for k, v in assignment.items() if k not in added}
    for k, v in json.loads(before).items():
        if json.dumps(after_existing[k], ensure_ascii=False, sort_keys=True) \
                != json.dumps(v, ensure_ascii=False, sort_keys=True):
            raise AssertionError(f"기존 배정 변경됨: {k}")

    CARD_OUT.write_bytes(bytes(card))
    doc["version"] = int(doc.get("version", 1)) + 1
    doc.setdefault("b2x_history", []).append(
        {"added": sorted(added), "card": CARD_OUT.name})
    ASSIGN.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(json.dumps({"status": "EXTEND_OK", "added": added,
                      "already_present": [c for c in chars
                                          if c not in new_chars],
                      "free_slots_left": len(free) - len(added),
                      "card": CARD_OUT.name,
                      "assignment_version": doc["version"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
