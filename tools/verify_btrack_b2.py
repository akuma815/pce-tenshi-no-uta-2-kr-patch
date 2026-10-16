#!/usr/bin/env python3
"""B2 풀 카드 독립 검증 — 배정표 기준 전수 대조."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BIOS_SRC = ROOT / "bios" / "Super CD-ROM2 System Ver. 3.00 (J).pce"
CARD = ROOT / "probes" / "SystemCard3_btrack_full.pce"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
MANIFEST = ROOT / "translation" / "btrack_b2_manifest.json"
FONT_BASE = 0x30000
GLYPH_BYTES = 18


def main() -> None:
    a = json.loads(ASSIGN.read_text(encoding="utf-8"))
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    orig = BIOS_SRC.read_bytes()[512:]
    card = CARD.read_bytes()
    failures = []

    if len(card) != 262_144:
        failures.append("카드 크기 오류")
    if hashlib.sha256(card).hexdigest() != m["card_sha256"]:
        failures.append("카드 sha256 불일치")

    # 폰트 시트에서 독립 재렌더해 카드 내용과 대조
    im = Image.open(a["font_sheet"]).convert("RGB")
    xoff = a["glyph_x_offset"]
    allowed = set()
    seen_idx = set()
    for ch, e in a["assignment"].items():
        idx = e["glyph_index"]
        if idx in seen_idx:
            failures.append(f"슬롯 중복: {idx}")
        seen_idx.add(idx)
        if not (453 <= idx <= 3417):
            failures.append(f"{ch}: kanji 구간 밖 슬롯 {idx}")
        gi = ord(ch) - 0xAC00
        cx, cy = (gi % 64) * 9, (gi // 64) * 12
        rows = []
        for y in range(12):
            row = 0
            for x in range(9):
                if im.getpixel((cx + x, cy + y)) != (0, 0, 0):
                    row |= 1 << (11 - (x + xoff))
            rows.append(row)
        expect = bytearray()
        for y in range(0, 12, 2):
            r0, r1 = rows[y], rows[y + 1]
            expect.extend((r0 >> 4, ((r0 & 0x0F) << 4) | (r1 >> 8), r1 & 0xFF))
        off = FONT_BASE + idx * GLYPH_BYTES
        if card[off:off + GLYPH_BYTES] != bytes(expect):
            failures.append(f"{ch}: 카드 글리프 불일치 @slot {idx}")
        allowed.update(range(off, off + GLYPH_BYTES))

    stray = [i for i in range(len(orig)) if orig[i] != card[i] and i not in allowed]
    if stray:
        failures.append(f"승인 외 변경 {len(stray)}B (첫: {hex(stray[0])})")
    diff = sum(1 for i in allowed if orig[i] != card[i])

    # 카드 UI 한자 슬롯 보존 확인
    for idx_s, ch in m["supply"]["card_ui_excluded"].items():
        off = FONT_BASE + int(idx_s) * GLYPH_BYTES
        if card[off:off + GLYPH_BYTES] != orig[off:off + GLYPH_BYTES]:
            failures.append(f"카드 UI 한자 {ch} 슬롯 변경됨")

    verdict = "PASS" if not failures else "FAIL"
    print(f"BTRACK B2 FULL CARD: {verdict} "
          f"({len(a['assignment'])}자 배정, diff {diff}B, 승인 외 0B 요구)")
    for f in failures[:10]:
        print("  -", f)
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
