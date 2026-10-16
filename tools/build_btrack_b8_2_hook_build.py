#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B8.2 — 씬 578(두 번째 마을, 비-96섹터 78섹터) 편입.

b8.1 대비 변경 (2026-08-24 설계, HANDOFF §1 / Z9_b8 문서 §4.2):
  1. **리더 v2: 인덱스 뱅크를 씬별 데이터로** — `LDA #INDEX_BANK` 를
     `LDA SCRATCH+4` 로 교체(+1B). 행 이미지의 **첫 행 = 인덱스 행** 규약을
     전 씬에 적용하면 SCRATCH+4 가 항상 그 씬의 인덱스 뱅크다.
     (578 의 extent 는 $68..$7B 전반 — $7E 인덱스는 extent 밖이라 불가.
      짧은 씬 규칙: 풀 뱅크 ⊆ 로드 extent, 복원 행이 씬 자신의 섹터여야 함)
  2. **씬 578 추가 (extent-내 하이브리드)**: $6A = 인덱스+armchk+텍스트,
     $6B = 텍스트, 초과분 = 카드 FF 스페어 + (부족 시) CDL-cold 00-run.
     풀 8섹터 = 9214..9221 (2882 풀 9206..9213 뒤).
  3. **레코드 dedupe**: 동일 encoded 바이트는 한 번만 저장(씬 내 다대일)
     + 2882 의 카드 상주 레코드와 동일하면 그 주소를 공유(씬 간 —
     카드는 상시 매핑 ROM 이라 컨텍스트 무관).

주의: 578 뱅크 근거는 seg_290_town2.cdl(=578 컨텍스트) 1캡처 — 게이트에서
마을 전 콘텐츠(NPC 전원·메뉴·건물)를 확인해야 한다.

출력: *_btrack_b8_2.bin/.cue + probes/SystemCard3_btrack_b8_2.pce
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_btrack_b7_hook_build import (
    Asm, make_slice, asm_bank81,
    T2, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP, WINDOW_LO, LOADER,
    SCRATCH, WINDOW_CODE_END, FLAG, TBANK, CURL, CURH,
    PRESENT, WINDOW_HI, INDEX_SECTORS, ROWS_IMG_LEN, ENTRY_LEN,
    BANK_SIZE, INDEX_MAGIC, TRAP,
    CARD_TABLE_OFF, SRC_BIN, SRC_SHA256, SRC_CUE, CARD_SRC, DISASM,
)
from build_btrack_b7_6_hook_build import (
    HY_LBA, HY_BASE, HY_SECTORS, HY_BANK_IDX, HY_BANK_TXT,
    CARD_TEXT_BINS, FONT_TAIL,
)
from build_btrack_b8_hook_build import (
    ARMCHK, INDEX_CAP, EXT_SECTORS, DATA_FRAMES, INS_OFF,
    asm_loader_v4, asm_armchk, shift_cue,
)

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b8_3"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b8_3.pce"
OUT_MANIFEST = ROOT / "translation" / "btrack_b8_3_hook_manifest.json"
ASSET_MAP = ROOT / "module_relink" / "z9_static_asset_map" / "manifest.json"

SECTOR = 2048

# ---- 씬 구성 -----------------------------------------------------------------
# uniform: (lba, base, [텍스트 뱅크...], index_bank) — 인덱스 뱅크 명시.
SCENES_UNIFORM = [(482, 9178, [0x7B, 0x7C, 0x7D], 0x7E),
                  (290, 9192, [0x76, 0x7F], 0x7E)]
# 하이브리드 2882: 578 과의 교집합 레코드(11,173B)를 **카드 bins 에 강제
# 배치**(prefer_card) — 두 씬이 같은 카드 주소를 공유한다.
# 하이브리드 578 (b8.3 재선정, 2026-08-24): play-CDL(town2) ∪ init-coverage
# 합집합 cold ∩ extent ∩ 비전역 = **{$76} 단 하나** (b8.2 의 $6A/$6B 는
# init 구간 그래픽 소스로 판명 — §9). $76 = 인덱스+armchk+텍스트 단일 뱅크,
# 초과분 = 카드 공유(교집합) + FF 스페어. 00-run 은 불필요해져 제외.
S578_LBA, S578_BASE = 578, 9214
S578_BANK_IDX = 0x76
S578_SECTORS = 78
# 578 의 카드 bin 은 상수가 아니라 **2882 배치 후 CARD_TEXT_BINS 잔여 FF
# 공간**에서 동적으로 산출한다 (prefer_card 로 2882 가 스페어까지 쓰므로).


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


# ---- 리더 v2 (인덱스 뱅크 = SCRATCH+4) ---------------------------------------

def asm_reader_v2(origin: int) -> Asm:
    a = Asm(origin)
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)
    a.emit(0xAD, (SCRATCH + 4) & 0xFF, (SCRATCH + 4) >> 8)  # 씬별 인덱스 뱅크
    a.emit(0x53, 0x20)
    a.jsr(ARMCHK)
    a.emit(0x68, 0x53, 0x20)
    a.branch(0xB0, "native")
    a.label("serve")
    a.emit(0x43, 0x20, 0x48)
    a.emit(0xAD, TBANK & 0xFF, TBANK >> 8, 0x53, 0x20)
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x85, 0x00)
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x85, 0x01)
    a.emit(0xB2, 0x00)
    a.branch(0xF0, "nul")
    a.emit(0x8D, 0x80, 0x2D)
    a.emit(0xEE, CURL & 0xFF, CURL >> 8)
    a.branch(0xD0, "nohi")
    a.emit(0xEE, CURH & 0xFF, CURH >> 8)
    a.label("nohi")
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x18, 0x60)
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)
    a.label("native")
    a.emit(0x38, 0x60)
    return a


# ---- 행 이미지 (인덱스 행 먼저 — 전 씬 공통 규약) -----------------------------

def rowset(rows) -> bytes:
    img = bytearray()
    for l, cnt, bank in rows:
        img += bytes(((l >> 16) & 0xFF, (l >> 8) & 0xFF, l & 0xFF, cnt, bank))
    img.append(0xFF)
    assert len(img) <= ROWS_IMG_LEN
    img.extend(b"\xFF" * (ROWS_IMG_LEN - len(img)))
    return bytes(img)


def rows_image(lba: int, base: int, tbanks: list[int], ibank: int,
               isec: int = INDEX_SECTORS) -> bytes:
    pool = rowset([(base + 4 * len(tbanks), isec, ibank)]
                  + [(base + i * 4, 4, b) for i, b in enumerate(tbanks)])
    restore = rowset([(lba + (ibank - 0x68) * 4, isec, ibank)]
                     + [(lba + (b - 0x68) * 4, 4, b) for b in tbanks])
    return pool + restore


def rows_image_2882() -> bytes:
    pool = rowset([(HY_BASE, 4, HY_BANK_IDX), (HY_BASE + 4, 4, HY_BANK_TXT)])
    restore = rowset([(HY_LBA + (HY_BANK_IDX - 0x68) * 4, 4, HY_BANK_IDX),
                      (HY_LBA + (HY_BANK_TXT - 0x68) * 4, 4, HY_BANK_TXT)])
    return pool + restore


def rows_image_578() -> bytes:
    """578 = $76 단일 뱅크 (행0 = 인덱스 행 규약 자동 충족)."""
    pool = rowset([(S578_BASE, 4, S578_BANK_IDX)])
    restore = rowset([(S578_LBA + (S578_BANK_IDX - 0x68) * 4, 4,
                       S578_BANK_IDX)])
    return pool + restore


# ---- 패킹 (dedupe + 공유 지원) ------------------------------------------------

def build_index(records, locate) -> bytes:
    buckets = {i: [] for i in range(24)}
    for r in records:
        key = int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
        kb, off13 = key >> 13, key & 0x1FFF
        bank, addr = locate(r)
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
    return bytes(index)


def pack_bins(records, bins, card: bytes, share: dict[str, tuple[int, int]],
              prefer_card: set[str] | None = None):
    """FFD 로 bins 에 배치. 동일 encoded 는 재사용(다대일), share 맵(카드
    상주 기존 주소) 히트 시 저장 없이 그 주소 사용. prefer_card 에 든 hex 는
    카드 bin 을 먼저 시도(씬 간 공유 대상 — 2026-08-24 b8.3).
    bins: (name, kind[ram|card], bank, in_bank_off, cap, fill[FF|00])"""
    for name, kind, bank, off, cap, fill in bins:
        if kind == "card":
            lo = bank * BANK_SIZE + off
            if set(card[lo:lo + cap]) != {fill}:
                raise ValueError(f"{name}: 카드 구간이 {fill:02X}-run 아님")
            fs, fe = FONT_TAIL
            if max(lo, fs) < min(lo + cap, fe):
                raise ValueError(f"{name}: 폰트 꼬리 침범")
    cursors = {b[0]: 0 for b in bins}
    placed: dict[str, tuple[str, int]] = {}     # hex -> (bin, off)
    order = sorted({r["encoded_hex"] for r in records},
                   key=lambda h: (-len(h), h))  # 결정적 FFD
    shared_hits = 0
    prefer_card = prefer_card or set()
    for h in order:
        if h in share:
            shared_hits += len(h) // 2
            continue
        data = bytes.fromhex(h)
        if 0 in data[:-1]:
            raise ValueError("내부 00")
        trial = (sorted(bins, key=lambda b: b[1] != "card")
                 if h in prefer_card else bins)
        for name, kind, bank, off, cap, fill in trial:
            if cursors[name] + len(data) <= cap:
                placed[h] = (name, cursors[name])
                cursors[name] += len(data)
                break
        else:
            raise ValueError(f"배치 공간 부족 ({len(data)}B): "
                             + json.dumps({b[0]: f"{cursors[b[0]]}/{b[4]}"
                                           for b in bins}))
    bin_by = {b[0]: b for b in bins}

    def locate_hex(h):
        if h in share:
            return share[h]
        name, o = placed[h]
        _, kind, bank, off, cap, fill = bin_by[name]
        return bank, 0xA000 + off + o

    stats = {b[0]: {"cap": b[4], "used": cursors[b[0]], "kind": b[1],
                    "bank": f"{b[2]:02X}"} for b in bins}
    stats["_shared_bytes"] = shared_hits
    return placed, locate_hex, stats, bin_by, cursors


def render_hybrid(records, armchk, bins, card, share, ibank_name_prefix,
                  prefer_card: set[str] | None = None):
    """인덱스뱅크(4섹터)+텍스트뱅크(4섹터) 이미지와 카드 패치 생성."""
    n_index = 2 + 48 + 7 * len(records) + 24
    if n_index > INDEX_CAP:
        raise ValueError(f"인덱스 {n_index}B > {INDEX_CAP:#x}")
    placed, locate_hex, stats, bin_by, cursors = \
        pack_bins(records, bins, card, share, prefer_card)
    index = build_index(records, lambda r: locate_hex(r["encoded_hex"]))
    assert len(index) == n_index
    imgs = {}
    for name, kind, bank, off, cap, fill in bins:
        if kind != "ram":
            continue
        img = imgs.setdefault(bank, bytearray(b"\x00" * BANK_SIZE))
        used = cursors[name]
        for h in sorted(placed, key=lambda h: placed[h][1]):
            if placed[h][0] == name:
                data = bytes.fromhex(h)
                o = placed[h][1]
                if off + o + len(data) > BANK_SIZE:
                    raise ValueError("ram bin 초과")
                img[off + o:off + o + len(data)] = data
        pad = bytearray(TRAP * ((cap - used) // 2 + 1))[:cap - used]
        img[off + used:off + cap] = pad
    card_patches = []
    for name, kind, bank, off, cap, fill in bins:
        if kind != "card":
            continue
        used = cursors[name]
        if not used:
            continue
        blob = bytearray(bytes([fill]) * used)
        for h, (nm, o) in placed.items():
            if nm == name:
                data = bytes.fromhex(h)
                blob[o:o + len(data)] = data
        card_patches.append((bank * BANK_SIZE + off, bytes(blob), name))
    return index, imgs, card_patches, stats, locate_hex


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 사전검증
    assert bytes(out[eng_off(VECTOR):eng_off(VECTOR) + 3]) == bytes((0x4C, 0x84, 0x42))
    slice_src = bytes(out[eng_off(SLICE_LO):eng_off(SLICE_HI)])
    assert slice_src[:4] == bytes((0xDA, 0xBD, 0x31, 0x65))
    assert slice_src[-2:] == bytes((0xD0, 0xD6))
    wnd_src = bytes(out[eng_off(WINDOW_LO):eng_off(WINDOW_HI)])
    assert set(wnd_src) == {0xFF}, "FF 창 오염"
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        nsec = 4 * len(tbanks) + INDEX_SECTORS
        seg = bytes(out[T2 + base * SECTOR: T2 + (base + nsec) * SECTOR])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"
    for base, nsec in ((HY_BASE, HY_SECTORS), (S578_BASE, 4)):
        seg = bytes(out[T2 + base * SECTOR: T2 + (base + nsec) * SECTOR])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"
    # 채택 뱅크 ⊆ 정적 지도 후보 (96섹터 씬) + 578 extent 규칙
    amap = json.loads(ASSET_MAP.read_text(encoding="utf-8"))
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        cand = set(amap["scene_verdicts"][str(lba)]["candidate_banks"])
        chosen = {f"{b:02X}" for b in tbanks} | {f"{ibank:02X}"}
        if not chosen <= cand:
            raise ValueError(f"scene {lba}: {sorted(chosen)} ⊄ {sorted(cand)}")
    assert {f"{HY_BANK_IDX:02X}", f"{HY_BANK_TXT:02X}"} <= \
        set(amap["scene_verdicts"][str(HY_LBA)]["candidate_banks"])
    # 578: extent 내 + 전역 배제 밖. 뱅크 근거 = play-CDL(town2) ∪
    # init-coverage(scene_init_coverage_578.tsv) 합집합 cold = {$76} 뿐
    # (2026-08-24 실측 — $6A/$6B 는 init 그래픽 소스로 판명, §9).
    excl = {int(b, 16) for b in amap["excluded_banks_all_scenes"]}
    for b in (S578_BANK_IDX,):
        assert b not in excl, f"578 뱅크 {b:02X} 는 전역 자산"
        assert (b - 0x68 + 1) * 0x2000 <= S578_SECTORS * SECTOR, \
            f"578 뱅크 {b:02X} 가 extent 밖"
    init_tsv = ROOT / "translation" / "scene_init_coverage_578.tsv"
    assert init_tsv.is_file(), "578 init coverage 없음 — 캡처 필요"
    n_scenes = len(SCENES_UNIFORM) + 2
    assert n_scenes * ENTRY_LEN + 1 <= FONT_TAIL[1] - FONT_TAIL[0]

    # 창 조립 (로더 v4 재사용 + 리더 v2)
    loader = asm_loader_v4().resolve()
    wnd_slice_addr = LOADER + len(loader)
    wslice = make_slice(slice_src)
    wnd_reader_addr = wnd_slice_addr + len(wslice)
    reader = asm_reader_v2(wnd_reader_addr).resolve()
    wnd_end = wnd_reader_addr + len(reader)
    if wnd_end > WINDOW_CODE_END:
        raise ValueError(f"창 코드 초과: {wnd_end:#06x}")
    bank81 = asm_bank81(wnd_slice_addr, wnd_reader_addr)
    armchk = asm_armchk()

    scene_stats = {}
    pool_patches = []
    card = bytearray(CARD_SRC.read_bytes())

    # 균일 씬 (dedupe 적용, 카드 미사용)
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        pl = json.loads((ROOT / "translation" /
                         (f"btrack_b7_scene_{lba}_payload.json"
                          if lba != 482 else "btrack_b4_field_payload.json")
                         ).read_text(encoding="utf-8"))["records"]
        n_index = 2 + 48 + 7 * len(pl) + 24
        armchk_end = INDEX_CAP + len(armchk)
        bins = [(f"u{lba}_t{b:02X}", "ram", b, 0, BANK_SIZE, 0xFF)
                for b in tbanks] + \
               [(f"u{lba}_ihi", "ram", ibank, armchk_end,
                 BANK_SIZE - armchk_end, 0xFF),
                (f"u{lba}_ilo", "ram", ibank, n_index,
                 INDEX_CAP - n_index, 0xFF)]
        index, imgs, cpatches, stats, _loc = render_hybrid(
            pl, armchk, bins, bytes(card), {}, f"u{lba}")
        assert not cpatches
        iimg = imgs[ibank]
        iimg[0:len(index)] = index
        iimg[INDEX_CAP:armchk_end] = armchk
        text_img = bytearray()
        for b in tbanks:
            text_img += imgs[b]
        pool_patches.append((T2 + base * SECTOR, bytes(text_img),
                             f"scene {lba} text"))
        pool_patches.append((T2 + (base + 4 * len(tbanks)) * SECTOR,
                             bytes(iimg[:INDEX_SECTORS * SECTOR]),
                             f"scene {lba} index"))
        scene_stats[str(lba)] = {"records": len(pl), "mode": "uniform",
                                 "pool_base": base, "bins": stats,
                                 "index_bytes": len(index)}

    # 2882 하이브리드 — 578 과의 교집합 레코드를 카드에 강제 배치(prefer_card)
    pl2882 = json.loads((ROOT / "translation" /
                         f"btrack_b7_scene_{HY_LBA}_payload.json"
                         ).read_text(encoding="utf-8"))["records"]
    pl578 = json.loads((ROOT / "translation" /
                        f"btrack_b7_scene_{S578_LBA}_payload.json"
                        ).read_text(encoding="utf-8"))["records"]
    shared_set = {r["encoded_hex"] for r in pl2882} & \
        {r["encoded_hex"] for r in pl578}
    n_index = 2 + 48 + 7 * len(pl2882) + 24
    armchk_end = INDEX_CAP + len(armchk)
    bins2882 = [("h2882_7F", "ram", HY_BANK_TXT, 0, BANK_SIZE, 0xFF),
                ("h2882_ihi", "ram", HY_BANK_IDX, armchk_end,
                 BANK_SIZE - armchk_end, 0xFF),
                ("h2882_ilo", "ram", HY_BANK_IDX, n_index,
                 INDEX_CAP - n_index, 0xFF)] + \
               [(f"h2882_c{s:05X}", "card", s // BANK_SIZE,
                 s & (BANK_SIZE - 1), e - s, 0xFF) for s, e in CARD_TEXT_BINS]
    index, imgs, cpatches, stats2882, loc2882 = render_hybrid(
        pl2882, armchk, bins2882, bytes(card), {}, "h2882",
        prefer_card=shared_set)
    iimg = imgs[HY_BANK_IDX]
    iimg[0:len(index)] = index
    iimg[INDEX_CAP:armchk_end] = armchk
    pool_patches.append((T2 + HY_BASE * SECTOR,
                         bytes(iimg) + bytes(imgs[HY_BANK_TXT]),
                         "scene 2882 hybrid pool"))
    card_written_blobs = list(cpatches)
    scene_stats[str(HY_LBA)] = {"records": len(pl2882), "mode": "hybrid",
                                "pool_base": HY_BASE, "bins": stats2882,
                                "index_bytes": len(index)}
    # 공유원: 2882 의 카드 상주 hex -> (bank, addr)
    share: dict[str, tuple[int, int]] = {}
    for r in pl2882:
        h = r["encoded_hex"]
        bank, addr = loc2882(h)
        if bank < 0x20:                      # 카드 뱅크만 공유 가능
            share[h] = (bank, addr)

    # 578 하이브리드 ($76 단일 뱅크 + 2882 카드 공유 + 잔여 FF 스페어)
    n_index = 2 + 48 + 7 * len(pl578) + 24
    card_after = bytearray(card)
    used_by = {}
    for lo, blob, name in cpatches:
        card_after[lo:lo + len(blob)] = blob
        used_by[lo] = len(blob)
    card_bins_578 = []
    for s, e in CARD_TEXT_BINS:
        s2 = s + used_by.get(s, 0)
        if e - s2 >= 64:
            card_bins_578.append((s2, e, 0xFF))
    # FF 총량으로는 공유 11.2K + 578 잔여 2.3K 를 못 담는다(실측 1.2KB 부족)
    # → 00-run(CDL 9캡처 ROM cold, 2026-08-23 실측)을 마지막 순위로 사용.
    # Z4-v2 교훈(씬 RAM 00-run)과 계층이 다르지만 잔여 리스크로 기록,
    # 게이트(새 마을 전 대사)가 최종 판정.
    card_bins_578.append((0x02D59E, 0x02E000, 0x00))
    bins578 = [("s578_ihi", "ram", S578_BANK_IDX, armchk_end,
                BANK_SIZE - armchk_end, 0xFF),
               ("s578_ilo", "ram", S578_BANK_IDX, n_index,
                INDEX_CAP - n_index, 0xFF)] + \
              [(f"s578_c{s:05X}", "card", s // BANK_SIZE, s & (BANK_SIZE - 1),
                e - s, fill) for s, e, fill in card_bins_578]
    index578, imgs578, cpatches578, stats578, _ = render_hybrid(
        pl578, armchk, bins578, bytes(card_after), share, "s578")
    iimg = imgs578[S578_BANK_IDX]
    iimg[0:len(index578)] = index578
    iimg[INDEX_CAP:armchk_end] = armchk
    pool_patches.append((T2 + S578_BASE * SECTOR, bytes(iimg),
                         "scene 578 hybrid pool"))
    card_written_blobs += cpatches578
    scene_stats[str(S578_LBA)] = {"records": len(pl578), "mode": "hybrid578",
                                  "pool_base": S578_BASE, "bins": stats578,
                                  "index_bytes": len(index578)}

    # 디스크 패치 + 확장
    patches = [(eng_off(VECTOR) + 1, bytes((TRAMP & 0xFF, TRAMP >> 8)), "vector"),
               (eng_off(SLICE_LO), bank81, "bank81"),
               (eng_off(WINDOW_LO), loader + wslice + reader, "window code"),
               (eng_off(FLAG), bytes(6), "state=0")] + pool_patches
    for off, data, _ in patches:
        assert off + len(data) <= INS_OFF
        out[off:off + len(data)] = data
    out[INS_OFF:INS_OFF] = bytes(EXT_SECTORS * SECTOR)
    OUT_BIN.write_bytes(bytes(out))
    OUT_CUE.write_text(shift_cue(SRC_CUE.read_text(encoding="ascii"),
                                 OUT_BIN.name, EXT_SECTORS), encoding="ascii")

    # 카드: 씬 테이블(4씬, 인덱스 행 먼저) + 텍스트 blob
    table = bytearray()
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        table.extend(((lba >> 8) & 0xFF, lba & 0xFF))
        table.extend(rows_image(lba, base, tbanks, ibank))
    table.extend(((HY_LBA >> 8) & 0xFF, HY_LBA & 0xFF))
    table.extend(rows_image_2882())
    table.extend(((S578_LBA >> 8) & 0xFF, S578_LBA & 0xFF))
    table.extend(rows_image_578())
    table.append(0xFF)
    assert set(card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)]) == {0xFF}
    card[CARD_TABLE_OFF:CARD_TABLE_OFF + len(table)] = table
    card_written = [(CARD_TABLE_OFF, len(table), "scene table")]
    for lo, blob, name in card_written_blobs:
        card[lo:lo + len(blob)] = blob
        card_written.append((lo, len(blob), name))
    CARD_OUT.write_bytes(bytes(card))
    src_card = CARD_SRC.read_bytes()
    declared = [(lo, lo + ln) for lo, ln, _ in card_written]
    for i, (x, y) in enumerate(zip(src_card, card)):
        if x != y and not any(s <= i < e for s, e in declared):
            raise ValueError(f"카드 diff 감사 실패 @{i:06X}")

    # 디스어셈블 검산 (로더 + 리더 v2)
    for name, addr, length in (("loader", LOADER, len(loader)),
                               ("reader", wnd_reader_addr, len(reader))):
        r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{addr:X}",
                            f"{eng_off(addr):X}", f"{length:X}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B8-2-HOOK-BUILD",
        "runtime_status": "PENDING",
        "changes_vs_b8_1": [
            "reader v2: index bank <- SCRATCH+4 (행 이미지 첫 행 = 인덱스 행)",
            "b8.3: scene 578 = $76 단일 뱅크 (play∪init coverage cold 재선정"
            " — b8.2 의 $6A/$6B 는 init 그래픽 소스로 FAIL)",
            "레코드 dedupe + 578∩2882 교집합을 카드에 강제 배치(prefer_card,"
            " 두 씬 공유)"],
        "scenes": scene_stats,
        "card": {"out": CARD_OUT.name,
                 "written": [{"off": f"{lo:06X}", "bytes": ln, "what": w}
                             for lo, ln, w in card_written]},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader), "free": WINDOW_CODE_END - wnd_end},
        "output_bin_sha256": sha256(out),
        "card_sha256": sha256(card),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK",
                      "window": manifest["window"],
                      "scenes": {k: {"rec": v["records"],
                                     "shared": v["bins"].get("_shared_bytes", 0)}
                                 for k, v in scene_stats.items()},
                      "s578_bins": {k: f"{v['used']}/{v['cap']}"
                                    for k, v in stats578.items()
                                    if k != "_shared_bytes"},
                      "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "sha256": manifest["output_bin_sha256"][:16]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
