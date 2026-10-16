#!/usr/bin/env python3
"""B트랙 b1 probe 독립 검증 — 빌더 출력을 원본과 바이트 단위로 전수 대조."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIOS_SRC = ROOT / "bios" / "Super CD-ROM2 System Ver. 3.00 (J).pce"
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
CARD = ROOT / "probes" / "SystemCard3_btrack_b1_50slot.pce"
PROBE_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b1_probe.bin"
MANIFEST = ROOT / "translation" / "btrack_b1_probe_manifest.json"

FONT_BASE = 0x30000
GLYPH_BYTES = 18
DATA_TRACK_OFFSET = 7_914_480


def diff_ranges(a: bytes, b: bytes):
    assert len(a) == len(b)
    out, start = [], None
    for i in range(len(a)):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(a)))
    return out


def main() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = []

    # ---- 카드 검증 ----------------------------------------------------------
    orig = BIOS_SRC.read_bytes()[512:]
    card = CARD.read_bytes()
    if len(card) != 262_144:
        failures.append("card 크기 오류")
    if hashlib.sha256(card).hexdigest() != m["card"]["sha256"]:
        failures.append("card sha256 매니페스트 불일치")

    allowed = set()
    for w in m["card"]["writes"]:
        idx = w["glyph_index"]
        off = FONT_BASE + idx * GLYPH_BYTES
        if off != w["rom_offset"]:
            failures.append(f"slot {idx} rom_offset 불일치")
        if not (1 <= idx <= 3417):
            failures.append(f"slot {idx} 실존 글리프 구간 밖")
        if orig[off:off + GLYPH_BYTES].hex() != w["original_hex"]:
            failures.append(f"slot {idx} 원본 hex 불일치")
        if card[off:off + GLYPH_BYTES].hex() != w["glyph_hex"]:
            failures.append(f"slot {idx} 기록 hex 불일치")
        allowed.update(range(off, off + GLYPH_BYTES))
    stray = [r for r in diff_ranges(orig, card)
             if not all(i in allowed for i in range(r[0], r[1]))]
    if stray:
        failures.append(f"card 승인 외 변경: {[(hex(a), hex(b)) for a, b in stray[:5]]}")
    card_diff = sum(1 for i in range(len(orig)) if orig[i] != card[i])

    # ---- 게임 검증 ----------------------------------------------------------
    ob = ORIGINAL_BIN.read_bytes()
    pb = PROBE_BIN.read_bytes()
    if len(ob) != len(pb):
        failures.append("BIN 크기 변화")
    if hashlib.sha256(pb).hexdigest() != m["game"]["bin_sha256"]:
        failures.append("game sha256 매니페스트 불일치")
    allowed_g = set()
    for w in m["game"]["writes"]:
        phys = DATA_TRACK_OFFSET + w["iso_offset"]
        if phys != w["physical_offset"]:
            failures.append("physical_offset 불일치")
        expected = bytes.fromhex(w["expected_hex"])
        if ob[phys:phys + len(expected)] != expected:
            failures.append(f"원문 hex 불일치 @iso {w['iso_offset']:#x}")
        repl = bytes.fromhex(w["replace_hex"])
        at = phys + w["replace_at"]
        if pb[at:at + len(repl)] != repl:
            failures.append(f"치환 hex 불일치 @iso {w['iso_offset']:#x}")
        # 치환 구간 밖 원문 보존
        if pb[phys:at] != ob[phys:at] or \
           pb[at + len(repl):phys + len(expected)] != ob[at + len(repl):phys + len(expected)]:
            failures.append(f"런 내부 비치환 구간 손상 @iso {w['iso_offset']:#x}")
        allowed_g.update(range(at, at + len(repl)))
    stray_g = [r for r in diff_ranges(ob, pb)
               if not all(i in allowed_g for i in range(r[0], r[1]))]
    if stray_g:
        failures.append(f"game 승인 외 변경: {[(hex(a), hex(b)) for a, b in stray_g[:5]]}")
    game_diff = sum(1 for i in allowed_g if ob[i] != pb[i])

    verdict = "PASS" if not failures else "FAIL"
    print(f"BTRACK B1 PROBE: {verdict} "
          f"(card slots {m['card']['slots_replaced']}, card diff {card_diff} B, "
          f"game diff {game_diff} B / 승인 18 B)")
    for f in failures:
        print("  -", f)
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
