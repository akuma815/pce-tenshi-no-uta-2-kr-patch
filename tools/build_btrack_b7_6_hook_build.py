#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B7.6 — 2882(탑) 카드 하이브리드 추가 (b7.5 + 3번째 씬).

배경 (HANDOFF §1, docs/active/Z9_정적_자산_지도_결과.md):
  2882 는 정적 자산 지도 배제 + 탑 CDL hot 을 빼면 후보 뱅크가 $7E/$7F 뿐
  (16,384B) < 텍스트 24,050B → RAM 단독 상주 불가. 초과분은 **시스템 카드
  ROM 의 free 구간**에 둔다. armchk 인덱스의 bank 필드에 카드 뱅크
  ($00-$1F)를 넣으면 serve 의 `TAM #$20` 이 그대로 카드 ROM 을 매핑하므로
  **리더/로더 코드는 b7 과 동일(무변경)** — 순수 데이터 확장이다.

카드 free 구간 소비 안전성 (2026-08-23 실측):
  카드 전체 FF/00 run ≥64B 합계 18,051B 를 재도출하고, CDL 9캡처(전 코스)의
  카드 'ROM' 블록 union(접근 8,473B — 로깅 살아있음 확인)과 교차 —
  **11개 run 전부 접근 0B (cold)**. 텍스트 배치는 그중 FF run 만 사용하고
  (00-run 은 §9 "반복 00 구간" 교훈상 회피), 폰트 꼬리(0x3F054..0x3FAE1)는
  씬 테이블 성장분(58씬 = 2,555B)을 위해 예약한다. 뱅크 $00 run 은 BIOS
  코어 뱅크라 보수적으로 제외.

2882 배치:
  - RAM 행 2개: pool_base+0 4섹터 → $7E (인덱스+armchk@0x780+텍스트 겸용),
    pool_base+4 4섹터 → $7F (텍스트). 복원 행 2개 = 원본 씬 섹터.
  - 카드 텍스트: 선언된 FF 구간에 FFD 패킹. 레코드는 bin(단일 뱅크) 내 연속.
  - 씬 테이블 엔트리 형식은 b7 과 동일(44B, 행 세트는 FF 종결이라 2행도 수용).

출력: *_btrack_b7_6.bin/.cue + probes/SystemCard3_btrack_b7_6.pce
(b7.5 산출물 무변경 유지 — 파생 빌드는 항상 새 파일명, 절대 규칙 #1)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_hook_build import (          # b7 코드 재사용 — 무변경
    Asm, asm_loader_v3, asm_reader, asm_bank81, asm_armchk, make_slice,
    pack_scene, scene_rows_image,
    T2, ENG, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP, WINDOW_LO, LOADER,
    SCRATCH, RESTORE_OFF, WINDOW_CODE_END, FLAG, PRESENT, WINDOW_HI,
    TEXT_SECTORS, INDEX_BANK, INDEX_SECTORS, ROWS_IMG_LEN, ENTRY_LEN,
    BANK_SIZE, INDEX_CAP, ARMCHK, INDEX_MAGIC, TRAP,
    CARD_TABLE_OFF, CARD_BANK, CARD_TABLE_LOGICAL,
    SRC_BIN, SRC_SHA256, SRC_CUE, CARD_SRC, DISASM,
)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b7_6"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b7_6.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b7_6_hook_manifest.json"
ASSET_MAP = ROOT / "module_relink" / "z9_static_asset_map" / "manifest.json"

# 균일 씬 (b7.5 그대로)
UNIFORM_SCENES = [(482, 9178, [0x7B, 0x7C, 0x7D]),
                  (290, 9192, [0x78, 0x79, 0x7A])]

# 하이브리드 씬 2882
HY_LBA = 2882
HY_BASE = 9206                       # 9178..9205 = 482/290 풀. 8섹터 사용
HY_SECTORS = 8
HY_BANK_IDX = 0x7E                   # 인덱스+armchk+텍스트 겸용
HY_BANK_TXT = 0x7F

# 카드 텍스트 bin (전부 원본 FF-run ∧ CDL-9캡처 ROM cold — 2026-08-23 실측,
# docs/active/Z9_정적_자산_지도_결과.md 후속 감사). 큰 구간 우선.
CARD_TEXT_BINS = [
    (0x02AB40, 0x02C000),            # bank $15, 5,312B
    (0x002CF9, 0x003C77),            # bank $01, 3,966B
    (0x007A50, 0x008000),            # bank $03, 1,456B
    (0x003C7A, 0x004000),            # bank $01, 902B
    (0x02FE43, 0x030000),            # bank $17, 445B
    (0x005F46, 0x006000),            # bank $02, 186B
]
FONT_TAIL = (0x3F054, 0x3FAE1)       # 씬 테이블 전용 예약 — 텍스트 금지


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def hybrid_rows_image() -> bytes:
    """2882 SCRATCH 이미지 42B: 풀 2행+FF+패딩(21B) + 복원 2행+FF+패딩(21B).
    RUN 루프는 FF 에서 멈추므로 2행 세트도 b7 로더가 그대로 처리한다."""
    def row(l, cnt, bank):
        return bytes(((l >> 16) & 0xFF, (l >> 8) & 0xFF, l & 0xFF, cnt, bank))
    def rowset(rows):
        img = bytearray()
        for r in rows:
            img += row(*r)
        img.append(0xFF)
        assert len(img) <= ROWS_IMG_LEN
        img.extend(b"\xFF" * (ROWS_IMG_LEN - len(img)))
        return bytes(img)
    pool = rowset([(HY_BASE, 4, HY_BANK_IDX), (HY_BASE + 4, 4, HY_BANK_TXT)])
    restore = rowset([(HY_LBA + (HY_BANK_IDX - 0x68) * 4, 4, HY_BANK_IDX),
                      (HY_LBA + (HY_BANK_TXT - 0x68) * 4, 4, HY_BANK_TXT)])
    return pool + restore


def pack_hybrid(records, armchk: bytes, card: bytes):
    """2882 레코드를 $7F / $7E 잔여 / 카드 FF bin 에 FFD 패킹.
    반환: ($7E 4섹터 이미지, $7F 4섹터 이미지, 카드패치 [(off, bytes)], 통계)."""
    n = len(records)
    index_len = 2 + 48 + 7 * n + 24
    if index_len > INDEX_CAP:
        raise ValueError(f"인덱스 {index_len}B > {INDEX_CAP:#x}")
    armchk_end = INDEX_CAP + len(armchk)

    # bin: (name, kind, bank, in_bank_off, capacity) — kind: ram7E/ram7F/card
    bins = [
        ("ram7F", "ram", HY_BANK_TXT, 0, BANK_SIZE),
        ("ram7E_hi", "ram", HY_BANK_IDX, armchk_end, BANK_SIZE - armchk_end),
        ("ram7E_lo", "ram", HY_BANK_IDX, index_len, INDEX_CAP - index_len),
    ] + [
        (f"card_{s:05X}", "card", s // BANK_SIZE, s & (BANK_SIZE - 1), e - s)
        for s, e in CARD_TEXT_BINS
    ]
    for name, kind, bank, off, cap in bins:
        if kind == "card":
            lo = bank * BANK_SIZE + off
            if set(card[lo:lo + cap]) != {0xFF}:
                raise ValueError(f"{name}: 카드 구간이 FF 아님")
            fs, fe = FONT_TAIL
            if max(lo, fs) < min(lo + cap, fe):
                raise ValueError(f"{name}: 폰트 꼬리 예약 구간 침범")

    cursors = {b[0]: 0 for b in bins}
    placed = {}                       # id -> (bin, offset_in_bin)
    for r in sorted(records, key=lambda r: -len(r["encoded_hex"])):
        data = bytes.fromhex(r["encoded_hex"])
        if 0 in data[:-1]:
            raise ValueError(f"{r['id']}: 내부 00")
        for name, kind, bank, off, cap in bins:
            if cursors[name] + len(data) <= cap:
                placed[r["id"]] = (name, cursors[name])
                cursors[name] += len(data)
                break
        else:
            raise ValueError(f"{r['id']}: 배치 공간 부족 ({len(data)}B)")

    bin_by_name = {b[0]: b for b in bins}

    def locate(rid):
        name, o = placed[rid]
        _, kind, bank, off, _ = bin_by_name[name]
        in_bank = off + o
        return bank, 0xA000 + in_bank, kind

    # 인덱스 (pack_scene 과 동일 구조)
    buckets = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, addr, _ = locate(r["id"])
        buckets[kb].append(((off13 >> 8) & 0x1F, off13 & 0xFF, bank,
                            addr, r["original_raw_length"]))
    entry_area = bytearray()
    ptrs = []
    base = 0xA000 + 2 + 24 * 2
    for kb in range(24):
        ptrs.append(base + len(entry_area))
        for oh, ol, bank, addr, ln in sorted(buckets[kb]):
            lm1 = ln - 1
            entry_area.extend((oh, ol, bank, addr & 0xFF, addr >> 8,
                               lm1 & 0xFF, lm1 >> 8))
        entry_area.append(0xFF)
    index = bytearray(INDEX_MAGIC)
    for p in ptrs:
        index.extend((p & 0xFF, p >> 8))
    index.extend(entry_area)
    assert len(index) == index_len, (len(index), index_len)

    # 이미지 조립
    img7e = bytearray(b"\x00" * BANK_SIZE)
    img7e[0:len(index)] = index
    img7e[INDEX_CAP:armchk_end] = armchk
    img7f = bytearray(TRAP * (BANK_SIZE // 2))
    card_patches = {}
    for r in records:
        data = bytes.fromhex(r["encoded_hex"])
        name, o = placed[r["id"]]
        _, kind, bank, off, _ = bin_by_name[name]
        if name == "ram7F":
            img7f[o:o + len(data)] = data
        elif kind == "ram":
            img7e[off + o:off + o + len(data)] = data
        else:
            card_patches.setdefault(name, {})[o] = data
    # $7E 미사용 텍스트 영역 트랩 채움
    for name, kind, bank, off, cap in bins:
        if kind == "ram" and bank == HY_BANK_IDX:
            used = cursors[name]
            pad = bytearray(TRAP * ((cap - used) // 2 + 1))[:cap - used]
            img7e[off + used:off + cap] = pad

    card_out = []
    for name, kind, bank, off, cap in bins:
        if kind != "card" or name not in card_patches:
            continue
        lo = bank * BANK_SIZE + off
        blob = bytearray(b"\xFF" * cursors[name])
        for o, data in card_patches[name].items():
            blob[o:o + len(data)] = data
        card_out.append((lo, bytes(blob), name))

    stats = {name: {"capacity": cap, "used": cursors[name],
                    "kind": kind, "bank": f"{bank:02X}"}
             for name, kind, bank, off, cap in bins}
    return bytes(img7e), bytes(img7f), card_out, stats, index_len


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 정적 자산 지도 전제 확인 (2882 후보 = $7E/$7F)
    amap = json.loads(ASSET_MAP.read_text(encoding="utf-8"))
    excl = set(amap["excluded_banks_all_scenes"])
    for b in (f"{HY_BANK_IDX:02X}", f"{HY_BANK_TXT:02X}"):
        if b in excl:
            raise ValueError(f"뱅크 {b} 는 전역 자산 배제 대상")
    cand = amap["scene_verdicts"][str(HY_LBA)]["candidate_banks"]
    assert set(cand) == {f"{HY_BANK_IDX:02X}", f"{HY_BANK_TXT:02X}"}, cand

    # 사전검증 (b7 동일)
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42))
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65))
    assert slice_src[-2:] == bytes((0xD0, 0xD6))
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창 오염"
    n_scenes = len(UNIFORM_SCENES) + 1
    assert n_scenes * ENTRY_LEN <= 240, "카드 테이블 Y 인덱스(8bit) 한계"
    for lba, base, tbanks in UNIFORM_SCENES:
        seg = bytes(out[T2 + base * 2048: T2 + (base + 14) * 2048])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"
    seg = bytes(out[T2 + HY_BASE * 2048: T2 + (HY_BASE + HY_SECTORS) * 2048])
    assert set(seg) == {0}, f"풀 base {HY_BASE}: 원본 00-fill 아님"

    # 창 조립 (b7 과 동일 코드 — 재사용)
    loader = asm_loader_v3().resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > WINDOW_CODE_END:
        raise ValueError(f"창 코드 초과: {wnd_end:#06x}")
    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)
    armchk = asm_armchk()

    # 균일 씬 풀
    scene_stats = {}
    pool_patches = []
    for lba, base, tbanks in UNIFORM_SCENES:
        pl = json.loads((ROOT / "translation" /
                         (f"btrack_b7_scene_{lba}_payload.json"
                          if lba != 482 else "btrack_b4_field_payload.json")
                         ).read_text(encoding="utf-8"))["records"]
        text_img, idx_img, tstats, ilen = pack_scene(pl, armchk, tbanks)
        pool_patches.append((T2 + base * 2048, text_img, f"scene {lba} text"))
        pool_patches.append((T2 + (base + TEXT_SECTORS) * 2048, idx_img,
                             f"scene {lba} index"))
        scene_stats[str(lba)] = {"records": len(pl), "text": tstats,
                                 "index_bytes": ilen, "pool_base": base,
                                 "mode": "uniform",
                                 "text_banks": [f"{b:02X}" for b in tbanks]}

    # 하이브리드 씬 2882
    card = bytearray(CARD_SRC.read_bytes())
    pl2882 = json.loads((ROOT / "translation" /
                         f"btrack_b7_scene_{HY_LBA}_payload.json"
                         ).read_text(encoding="utf-8"))["records"]
    img7e, img7f, card_text, hstats, hy_index_len = \
        pack_hybrid(pl2882, armchk, bytes(card))
    pool_patches.append((T2 + HY_BASE * 2048, img7e + img7f,
                         f"scene {HY_LBA} hybrid pool"))
    scene_stats[str(HY_LBA)] = {
        "records": len(pl2882), "mode": "hybrid", "pool_base": HY_BASE,
        "index_bytes": hy_index_len, "bins": hstats,
        "text_total": sum(len(r["encoded_hex"]) // 2 for r in pl2882),
    }

    # 디스크 패치
    patches = [(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8)), "vector"),
               (eng_off(SLICE_LO), bank81, "bank81"),
               (eng_off(WINDOW_LO), loader + wslice + reader, "window code"),
               (eng_off(FLAG), bytes(6), "state=0")] + pool_patches
    for off, data, _ in patches:
        out[off:off + len(data)] = data
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(SRC_CUE.read_text(encoding="ascii")
                       .replace("Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin",
                                OUT_BIN.name), encoding="ascii")

    # 카드: 씬 테이블(3씬) + 2882 텍스트
    table = bytearray()
    for lba, base, tbanks in UNIFORM_SCENES:
        table.extend(((lba >> 8) & 0xFF, lba & 0xFF))
        table.extend(scene_rows_image(lba, base, tbanks))
    table.extend(((HY_LBA >> 8) & 0xFF, HY_LBA & 0xFF))
    table.extend(hybrid_rows_image())
    table.append(0xFF)
    assert set(card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)]) == {0xFF}, \
        "카드 테이블 자리 FF 아님"
    card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)] = table
    card_written = [(CARD_TABLE_OFF, len(table), "scene table")]
    for lo, blob, name in card_text:
        assert set(card[lo:lo + len(blob)]) == {0xFF}, f"{name}: FF 아님"
        card[lo:lo + len(blob)] = blob
        card_written.append((lo, len(blob), name))
    CARD_OUT.write_bytes(bytes(card))

    # 카드 diff 감사: 변경이 선언 범위 안에만 있는지
    src_card = CARD_SRC.read_bytes()
    declared = [(lo, lo + ln) for lo, ln, _ in card_written]
    for i, (a, b) in enumerate(zip(src_card, card)):
        if a != b and not any(s <= i < e for s, e in declared):
            raise ValueError(f"카드 diff 감사 실패: 선언 밖 변경 @{i:06X}")

    # 디스어셈블 검산 (창 로더 — b7 동일 코드지만 새 bin 에서 재검증)
    r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{LOADER:X}",
                        f"{eng_off(LOADER):X}", f"{len(loader):X}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"loader disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B7-6-HOOK-BUILD",
        "runtime_status": "PENDING",
        "scenes": scene_stats,
        "card": {"out": CARD_OUT.name,
                 "written": [{"off": f"{lo:06X}", "bytes": ln, "what": w}
                             for lo, ln, w in card_written],
                 "table_entries": n_scenes},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader), "free": WINDOW_CODE_END - wnd_end},
        "safety_evidence": {
            "card_bins": "원본 FF-run ∧ CDL 9캡처 ROM 접근 0B (2026-08-23)",
            "asset_map": amap["iso_sha256"][:16],
        },
        "output_bin_sha256": sha256(out),
        "card_sha256": sha256(card),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK",
                      "scenes": {k: v["records"] for k, v in scene_stats.items()},
                      "hybrid_bins": {k: f"{v['used']}/{v['capacity']}"
                                      for k, v in hstats.items()},
                      "card_written": manifest["card"]["written"],
                      "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "sha256": manifest["output_bin_sha256"][:16]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
