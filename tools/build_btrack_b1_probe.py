#!/usr/bin/env python3
"""B트랙 b1 — 실존 한자 슬롯 50개 교체 + 첫 대사 3런 SJIS 재인코딩 probe.

목적 (전략_재검토_BIOS폰트_2026-08-22.md §7 실험 3):
  - 시스템카드 mode-1 폰트의 실존 한자 슬롯 50개를 Galmuri 한글로 교체해도
    카드 부트·자체 UI·인게임 전 경로가 정상인지 검증한다.
  - 게임 스트림에는 검증된 "동일 길이 2바이트 치환"만 사용한다 (패딩 0바이트,
    유닛 경계 보존 — exact_substitution_probe PASS 메커니즘의 확장).

원본 무수정 원칙: 원본 BIN/CUE/BIOS는 읽기만 하고, 출력은 전부 새 파일이다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BIOS_SRC = ROOT / "bios" / "Super CD-ROM2 System Ver. 3.00 (J).pce"  # 512B 헤더 포함
EXPECTED_BIOS_SHA1 = "79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c"      # 헤더 제거 후
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
ORIGINAL_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
EXPECTED_BIN_SHA256 = "d16d29eb80b1b74a2ec929924349256b50b8f9f5c9a3fa37b6fcc08b059b22c5"
FONT_TTF = ROOT / "font" / "Galmuri11-Condensed.ttf"

OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b1_50slot.pce"       # 헤더 없는 262,144B
OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b1_probe"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_MANIFEST = ROOT / "translation" / "btrack_b1_probe_manifest.json"

DATA_TRACK_OFFSET = 7_914_480   # LBA 3365 — Track02 시작 (MODE1/2048 cooked)
FONT_BASE = 0x30000             # mode-1 폰트 시작 (ROM 오프셋, 헤더 제외)
GLYPH_BYTES = 18
REAL_GLYPH_MAX = 3417           # 실존 글리프 슬롯 상한 (2026-08-22 실측)

# ---- 한글 50자: 게임 치환에 쓰는 9자 + 카드 커버리지용 필러 41자 -----------------
GAME_CHARS = "여어준비는됐나뭐가"
FILLER_CHARS = "이아지리을다마트페도은에그기사고라니서있하물면야의게를시로해들대와으인보계상오요한"
ALL_CHARS = GAME_CHARS + FILLER_CHARS
assert len(ALL_CHARS) == 50 and len(set(ALL_CHARS)) == 50

# ---- 게임 치환 3런: 기존 매니페스트에서 검증된 원문 hex, 유닛 경계 보존 ----------
# 유닛 경계 근거: exact_substitution_probe(PASS)와 two_glyph 매니페스트의 동일 위치
# 치환 이력. 치환 구간은 반드시 원문 유닛(1B 토큰/2B SJIS)의 정수 배 길이다.
GAME_RUNS = [
    {   # おっす、シオン → 여어シオン   ([6F][2D][8141] 4B → 한글 2자)
        "iso_offset": 0x10B9F2, "expected_hex": "6F2D8141BCB5DD",
        "replace_at": 0, "replace_len": 4, "hangul": "여어",
    },
    {   # 支度は出来たのか → 준비는됐나のか  (선두 6유닛 10B → 한글 5자)
        "iso_offset": 0x10BA04, "expected_hex": "8E789378568F6F9788465532CCAAB2C4",
        "replace_at": 0, "replace_len": 10, "hangul": "준비는됐나",
    },
    {   # え、支度らに… 중 [8E78][9378] 4B → 뭐가
        "iso_offset": 0x10BA20, "expected_hex": "5F81418E7893784A4D517A474A388148",
        "replace_at": 3, "replace_len": 4, "hangul": "뭐가",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render_glyph(ch: str, font: ImageFont.FreeTypeFont) -> bytes:
    """one_glyph probe에서 런타임 검증된 12x12/18B 인코더 (원본 그대로)."""
    image = Image.new("1", (12, 12), 0)
    draw = ImageDraw.Draw(image)
    width = font.getmask(ch).size[0]
    draw.text((max(0, (12 - width) // 2), 1), ch, font=font, fill=1)
    pixels = image.load()
    rows: list[int] = []
    for y in range(12):
        row = 0
        for x in range(12):
            if pixels[x, y]:
                row |= 1 << (11 - x)
        rows.append(row)
    out = bytearray()
    for y in range(0, 12, 2):
        row0, row1 = rows[y:y + 2]
        out.extend((row0 >> 4, ((row0 & 0x0F) << 4) | (row1 >> 8), row1 & 0xFF))
    if len(out) != GLYPH_BYTES:
        raise AssertionError("mode-1 glyph encoder returned the wrong size")
    return bytes(out)


def main() -> None:
    # ---- 입력 고정 ----------------------------------------------------------
    bios_raw = BIOS_SRC.read_bytes()
    if len(bios_raw) != 262_656:
        raise ValueError("헤더 포함 262,656B 시스템카드가 아니다")
    bios = bytearray(bios_raw[512:])
    if hashlib.sha1(bytes(bios)).hexdigest() != EXPECTED_BIOS_SHA1:
        raise ValueError("시스템카드 SHA-1 불일치")
    if sha256(ORIGINAL_BIN) != EXPECTED_BIN_SHA256:
        raise ValueError("원본 BIN SHA-256 불일치")

    from analyze_system_card_font_slots import glyph_index  # noqa: E402
    if glyph_index("出".encode("shift_jis"), bytes(bios)) != 1722:
        raise AssertionError("glyph_index 회귀: 出 != 1722")

    # ---- 슬롯 50개 선정: 亜(0x889F)부터 연속 SJIS 한자 코드 -------------------
    assignments = []           # (hangul, sjis_bytes, glyph_index)
    lead, trail = 0x88, 0x9F
    for ch in ALL_CHARS:
        while True:
            code = bytes((lead, trail))
            idx = glyph_index(code, bytes(bios))
            trail += 1
            if trail == 0x7F:
                trail += 1
            if trail > 0xFC:
                trail = 0x40
                lead += 1
            if idx is not None and 1 <= idx <= REAL_GLYPH_MAX:
                slot = bios[FONT_BASE + idx * GLYPH_BYTES:FONT_BASE + (idx + 1) * GLYPH_BYTES]
                if any(b not in (0x00, 0xFF) for b in slot):   # 실존 글리프만
                    assignments.append((ch, code, idx))
                    break
    indices = [a[2] for a in assignments]
    if len(set(indices)) != 50:
        raise AssertionError("글리프 index 중복")

    # ---- 카드 빌드 ----------------------------------------------------------
    font = ImageFont.truetype(str(FONT_TTF), 11)
    card_writes = []
    for ch, code, idx in assignments:
        off = FONT_BASE + idx * GLYPH_BYTES
        original_hex = bytes(bios[off:off + GLYPH_BYTES]).hex()
        glyph = render_glyph(ch, font)
        if glyph == b"\x00" * GLYPH_BYTES:
            raise AssertionError(f"빈 글리프 렌더: {ch}")
        bios[off:off + GLYPH_BYTES] = glyph
        card_writes.append({
            "hangul": ch, "sjis": code.hex().upper(), "glyph_index": idx,
            "rom_offset": off, "original_hex": original_hex, "glyph_hex": glyph.hex(),
        })
    OUT_CARD.write_bytes(bytes(bios))

    # ---- 게임 빌드: 동일 길이 치환, 패딩 0 -----------------------------------
    sjis_of = {ch: code for ch, code, _ in assignments}
    game = bytearray(ORIGINAL_BIN.read_bytes())
    game_writes = []
    for run in GAME_RUNS:
        phys = DATA_TRACK_OFFSET + run["iso_offset"]
        expected = bytes.fromhex(run["expected_hex"])
        if game[phys:phys + len(expected)] != expected:
            raise ValueError(f"원문 불일치 @iso {run['iso_offset']:#x}")
        repl = b"".join(sjis_of[c] for c in run["hangul"])
        if len(repl) != run["replace_len"]:
            raise AssertionError("치환 길이 불일치")
        at = phys + run["replace_at"]
        game[at:at + len(repl)] = repl
        game_writes.append({
            "iso_offset": run["iso_offset"], "physical_offset": phys,
            "expected_hex": run["expected_hex"],
            "replace_at": run["replace_at"], "replace_hex": repl.hex().upper(),
            "hangul": run["hangul"],
        })
    if len(game) != ORIGINAL_BIN.stat().st_size:
        raise AssertionError("BIN 크기 변화")
    OUT_BIN.write_bytes(bytes(game))
    OUT_CUE.write_text(
        ORIGINAL_CUE.read_text(encoding="ascii").replace(ORIGINAL_BIN.name, OUT_BIN.name),
        encoding="ascii")

    # ---- 매니페스트 ---------------------------------------------------------
    manifest = {
        "format": "BTRACK-B1-50SLOT-PROBE",
        "runtime_status": "PENDING",
        "purpose": "실존 한자 슬롯 50개 한글 교체 + 첫 대사 3런 동일 길이 SJIS 치환. "
                   "PASS 시 B안(BIOS 폰트) 트랙 확정 근거.",
        "input": {
            "original_bios_sha1": EXPECTED_BIOS_SHA1,
            "original_bin_sha256": EXPECTED_BIN_SHA256,
        },
        "card": {
            "path": str(OUT_CARD), "sha256": sha256(OUT_CARD),
            "slots_replaced": len(card_writes),
            "expected_diff_bytes": sum(
                sum(1 for a, b in zip(bytes.fromhex(w["original_hex"]),
                                      bytes.fromhex(w["glyph_hex"])) if a != b)
                for w in card_writes),
            "writes": card_writes,
        },
        "game": {
            "bin": str(OUT_BIN), "bin_sha256": sha256(OUT_BIN),
            "cue": str(OUT_CUE),
            "expected_writes": len(game_writes),
            "expected_diff_bytes": 18,
            "writes": game_writes,
        },
        "runtime_gate": [
            "카드 부트 화면 정상 (자동 캡처 대조)",
            "부트 화면에서 카드 자체 UI(백업 관리) 진입 화면 정상 — 실험 2 겸용",
            "첫 대사: 여어シオン / 준비는됐나のか… / え、뭐가… 표시",
            "Memo 진입·복귀, 첫 전투, 필드 복귀, 탑 진입, 초상화 정상",
            "화면 깨짐·EXEC BRK·멈춤·오디오 이상 0건",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({
        "status": "BUILD_OK",
        "card": OUT_CARD.name, "card_sha256": manifest["card"]["sha256"][:16],
        "slots": len(card_writes),
        "slot_index_range": [min(indices), max(indices)],
        "game": OUT_BIN.name, "game_diff_bytes": 18,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
