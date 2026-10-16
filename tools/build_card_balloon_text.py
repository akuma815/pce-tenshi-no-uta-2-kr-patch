#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카드 미니게임 말풍선 텍스트(master_text category=card) 제자리 인코드 + 카드 16x16 글리프 보충.

- 모듈 안 SJIS 문자열(2B 문자, 0D 줄바꿈, 00 종료)을 같은 길이로 덮어쓴다: 한글 → 폰트 배정 2B 코드,
  반각 스페이스 → 8140(전각), \n → 0D, ?!,. → 전각 기호, 나머지는 SJIS 그대로. 남는 자리는 00.
- 줄당 셀 수 ≤ MAX_CELLS(원문 최장 14) — 넘치면 말풍선 밖에 그려지고 다음 페이지에 남는다(b29 실측 「다」).
- 쓰인 음절 중 카드 16x16 폰트(0x10000 + glyph_index*32)에 아직 없는 것은 Galmuri14 로 렌더해 새 카드 소스로 저장.
출력: translation/btrack_b30_card_balloon.json (디스크 패치 iso_off/old_hex/new_hex), 카드 CARD_OUT.
"""
from __future__ import annotations
import csv, io, json, sys
from pathlib import Path
from PIL import Image, ImageFont, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.argv = ["x"]
from build_btrack_b7_hook_build import T2
import analyze_system_card_font_slots as fs

MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
CARD_IN = ROOT / "probes" / "SystemCard3_btrack_full_v5.pce"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_full_v6.pce"
OUT = ROOT / "translation" / "btrack_b30_card_balloon.json"
FONT = r"G:\Downloads\Korean Traslate Project\Font\Galmuri14.ttf"
MAX_CELLS = 14
PUNCT = {"?": b"\x81\x48", "!": b"\x81\x49", ",": b"\x81\x41", ".": b"\x81\x42", "~": b"\x81\x60", "…": b"\x81\x63", " ": b"\x81\x40"}


def render16(ch, dx, dy):
    f = ImageFont.truetype(FONT, 15)   # Galmuri14 원 픽셀 = 15px (14 로 렌더하면 획이 빠짐 — 2026-10-11 수정; b37+ 는 font_compact.render16 이 글리프를 만든다)
    im = Image.new("L", (16, 16), 0); d = ImageDraw.Draw(im)
    bb = f.getbbox(ch); d.text((dx - bb[0] + (16 - (bb[2] - bb[0])) // 2, dy - bb[1] + (16 - (bb[3] - bb[1])) // 2), ch, font=f, fill=255)
    px = im.load(); out = bytearray(32)
    for y in range(16):
        v = 0
        for x in range(16):
            if px[x, y] > 128: v |= 0x8000 >> x
        out[y * 2] = v >> 8; out[y * 2 + 1] = v & 0xFF
    return bytes(out)


def main():
    asg = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    iso = open(ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin", "rb").read()[T2:]
    card = bytearray(CARD_IN.read_bytes())
    rows = [r for r in csv.reader(io.open(MASTER, encoding="utf-8", newline=""))]
    hdr = rows[0]; I = {h.lstrip("\ufeff"): i for i, h in enumerate(hdr)}
    patches, used = [], set()
    for r in rows[1:]:
        if r[I["category"]] != "card" or not r[I["translation"]].strip(): continue
        ko = r[I["translation"]]
        if ko == r[I["original"]]: continue                       # 오검출 행(원문 그대로)
        off = int(r[I["iso_offset"]], 16); raw = bytes.fromhex(r[I["raw_hex"]])
        assert iso[off:off + len(raw)] == raw, f"원본 불일치 {r[0]}"
        enc = bytearray(); cells = 0
        for ch in ko.replace(chr(92) + "n", "\n"):
            if ch == "\n":
                assert cells <= MAX_CELLS, f"{r[0]}: 줄 {cells}셀 > {MAX_CELLS}"
                enc.append(0x0D); cells = 0; continue
            if 0xAC00 <= ord(ch) <= 0xD7A3:
                assert ch in asg, f"{r[0]}: 미배정 음절 {ch}"
                enc += bytes.fromhex(asg[ch]["sjis"]); used.add(ch)
            elif ch in PUNCT: enc += PUNCT[ch]
            else: enc += ch.encode("shift_jis")
            cells += 1
        assert cells <= MAX_CELLS, f"{r[0]}: 마지막 줄 {cells}셀 > {MAX_CELLS}"
        assert len(enc) + 1 <= len(raw), f"{r[0]}: {len(enc)+1}B > 원문 {len(raw)}B"
        new = bytes(enc) + b"\x00" * (len(raw) - len(enc))
        patches.append({"iso_off": off, "old_hex": raw.hex().upper(), "new_hex": new.hex().upper(), "id": f"card@{off:07X}", "mode": "bytes", "ko": ko})
    # 글리프 보충: 카드에 비어 있는(또는 원본 가나 그대로인) 슬롯만. 기존 글리프와 렌더 정렬을 맞추기 위해 '이' 로 보정.
    def slot(ch):
        code = bytes.fromhex(asg[ch]["sjis"]); idx = fs.glyph_index((code[0], code[1]), card)
        assert idx is not None, ch
        return 0x10000 + idx * 32
    ref = card[slot("이"):slot("이") + 32]
    best = min(((dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)), key=lambda o: sum(bin(a ^ b).count("1") for a, b in zip(render16("이", *o), ref)))
    print("보정 오프셋", best, "불일치 비트", sum(bin(a ^ b).count("1") for a, b in zip(render16("이", *best), ref)))
    added = []
    for ch in sorted(used):
        s = slot(ch); cur = card[s:s + 32]; new = render16(ch, *best)
        if cur != new and (ch not in ("이",)):
            # b28 이 이미 쓴 글리프는 보정 렌더와 동일해야 한다; 다르면 새 음절로 간주해 기록
            added.append(ch); card[s:s + 32] = new
    CARD_OUT.write_bytes(bytes(card))
    OUT.write_text(json.dumps({"format": "CARD-BALLOON-TEXT-B30", "font": "Galmuri14 14px -> 16x16 at card 0x10000+idx*32", "card_src": CARD_IN.name, "card_out": CARD_OUT.name,
                               "syllables": "".join(sorted(used)), "glyphs_written": "".join(added), "patches": patches}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("rows", len(patches), "syllables", len(used), "glyphs written", len(added), "".join(added))


if __name__ == "__main__":
    main()
