#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B9-PoC — 확장 뱅크($20+) CPU read 실증 빌드.

b8.3 과의 유일한 차이 (2026-08-28 설계, Z9_b9_카드_확장_설계.md §1·§5-1):
  1. 카드를 512KB 로 확장 (b8.3 카드 + FF 256KB — 부팅 PASS 실증 구성과 동일,
     단 뱅크 머리 매직 대신 실 텍스트 배치).
  2. 씬 482 의 첫 대사 레코드(iso:010B9E7, "여어、시온… 준비는 다 됐나")
     **1개만** 카드 뱅크 $20 오프셋 0 에 배치(prefer_card) — 인덱스 엔트리가
     (bank=$20, addr=$A000) 을 가리킨다. 나머지 전 레코드·씬·훅은 b8.3 동일.

판정 (부팅 PASS 는 "거부 안 함"까지만 — 이 빌드가 read 를 실증):
  - PASS: 새 게임 첫 대사가 b8.3 과 동일한 한글로 표시 + serve 중 TBANK=$20 관측.
  - FAIL: 첫 대사만 깨짐(미러링이면 BIOS 바이트, open bus 면 FF류) — 다른
    대사는 전부 정상이어야 한다 (단일 레코드 격리 설계).

출력: *_btrack_b9poc.bin/.cue + probes/SystemCard3_btrack_b9poc.pce (512KB)
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
    make_slice, asm_bank81,
    T2, eng_off, VECTOR, SLICE_LO, SLICE_HI, TRAMP, WINDOW_LO, LOADER,
    FLAG, WINDOW_CODE_END, WINDOW_HI, INDEX_SECTORS, ENTRY_LEN,
    BANK_SIZE, CARD_TABLE_OFF, SRC_BIN, SRC_SHA256, SRC_CUE, CARD_SRC, DISASM,
)
from build_btrack_b7_6_hook_build import (
    HY_LBA, HY_BASE, HY_BANK_IDX, HY_BANK_TXT, CARD_TEXT_BINS, FONT_TAIL,
)
from build_btrack_b8_hook_build import (
    INDEX_CAP, EXT_SECTORS, INS_OFF, asm_loader_v4, asm_armchk, shift_cue,
)
from build_btrack_b8_2_hook_build import (
    SCENES_UNIFORM, S578_LBA, S578_BASE, S578_BANK_IDX, S578_SECTORS,
    asm_reader_v2, rows_image, rows_image_2882, rows_image_578, render_hybrid,
)

# 변형 프로브: argv = [card_kb] [poc_bank_hex]  (기본 512 20 = 원 PoC).
# 예: 768 4B → 768KB 카드 + 뱅크 $4B 서브 (b9 실사용 최원단 뱅크 실증).
_KB = int(sys.argv[1]) if len(sys.argv) > 1 else 512
_BK = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x20
_SUF = "" if (_KB, _BK) == (512, 0x20) else f"_{_KB}k{_BK:02X}"

OUT_STEM = f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b9poc{_SUF}"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
CARD_OUT = ROOT / "probes" / f"SystemCard3_btrack_b9poc{_SUF}.pce"
OUT_MANIFEST = ROOT / "translation" / f"btrack_b9poc{_SUF}_manifest.json"
ASSET_MAP = ROOT / "module_relink" / "z9_static_asset_map" / "manifest.json"

SECTOR = 2048
CARD_EXT_SIZE = _KB * 1024          # 512KB = boottest 실증 크기, 768KB = b9 후보
POC_BANK = _BK                      # 확장 뱅크 — read 실증 대상
POC_RECORD_ID = "iso:010B9E7"       # 새 게임 첫 대사 (source key E7A901)


def sha256(b) -> str:
    return hashlib.sha256(bytes(b)).hexdigest()


def main() -> None:
    out = bytearray(SRC_BIN.read_bytes())
    if sha256(out).upper() != SRC_SHA256:
        raise ValueError("원본 BIN 해시 불일치")

    # 사전검증 (b8.3 동일)
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
    for base, nsec in ((HY_BASE, 8), (S578_BASE, 4)):
        seg = bytes(out[T2 + base * SECTOR: T2 + (base + nsec) * SECTOR])
        assert set(seg) == {0}, f"풀 base {base}: 원본 00-fill 아님"
    amap = json.loads(ASSET_MAP.read_text(encoding="utf-8"))
    for lba, base, tbanks, ibank in SCENES_UNIFORM:
        cand = set(amap["scene_verdicts"][str(lba)]["candidate_banks"])
        chosen = {f"{b:02X}" for b in tbanks} | {f"{ibank:02X}"}
        if not chosen <= cand:
            raise ValueError(f"scene {lba}: {sorted(chosen)} ⊄ {sorted(cand)}")
    assert {f"{HY_BANK_IDX:02X}", f"{HY_BANK_TXT:02X}"} <= \
        set(amap["scene_verdicts"][str(HY_LBA)]["candidate_banks"])
    excl = {int(b, 16) for b in amap["excluded_banks_all_scenes"]}
    assert S578_BANK_IDX not in excl
    assert (S578_BANK_IDX - 0x68 + 1) * 0x2000 <= S578_SECTORS * SECTOR
    init_tsv = ROOT / "translation" / "scene_init_coverage_578.tsv"
    assert init_tsv.is_file(), "578 init coverage 없음"
    n_scenes = len(SCENES_UNIFORM) + 2
    assert n_scenes * ENTRY_LEN + 1 <= FONT_TAIL[1] - FONT_TAIL[0]

    # 창 조립 (b8.3 동일 — 로더 v4 + 리더 v2)
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

    # 카드: b8.3 소스 카드 + FF 확장 (512KB)
    card = bytearray(CARD_SRC.read_bytes())
    assert len(card) == 256 * 1024, f"카드 소스 {len(card)}B ≠ 256KB"
    card.extend(b"\xFF" * (CARD_EXT_SIZE - len(card)))

    scene_stats = {}
    pool_patches = []
    card_written_blobs = []
    poc_info = None

    # 균일 씬 — 482 만 PoC 카드 bin($20) 추가 + 첫 대사 레코드 prefer_card
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
        prefer = None
        if lba == 482:
            poc_rec = next(r for r in pl if r["id"] == POC_RECORD_ID)
            poc_hex = poc_rec["encoded_hex"]
            # 첫 대사가 다른 레코드와 dedupe 로 합쳐지지 않음을 확인
            # (합쳐지면 카드 배치가 그 레코드들도 $20 으로 끌고 간다 —
            #  PoC 격리 유지엔 무해하지만 명시적으로 개수를 기록)
            n_same = sum(1 for r in pl if r["encoded_hex"] == poc_hex)
            bins = bins + [("u482_cx20", "card", POC_BANK, 0, BANK_SIZE, 0xFF)]
            prefer = {poc_hex}
        index, imgs, cpatches, stats, _loc = render_hybrid(
            pl, armchk, bins, bytes(card), {}, f"u{lba}", prefer_card=prefer)
        if lba == 482:
            # 카드 패치 = PoC 레코드 1건 @0x40000 뿐이어야 한다
            assert len(cpatches) == 1, f"482 카드 패치 {len(cpatches)}건"
            lo, blob, name = cpatches[0]
            assert name == "u482_cx20" and lo == POC_BANK * BANK_SIZE
            assert blob == bytes.fromhex(poc_hex), "PoC blob 불일치"
            card_written_blobs += cpatches
            poc_info = {"record_id": POC_RECORD_ID,
                        "source_key_u24le": poc_rec["source_key_u24le"],
                        "card_off": f"{lo:06X}", "bank": f"{POC_BANK:02X}",
                        "addr": "A000", "bytes": len(blob),
                        "dedupe_aliases": n_same,
                        "ko_preview": poc_rec["ko_repaginated"][:40]}
        else:
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
    assert poc_info is not None

    # 2882 하이브리드 (b8.3 동일 — prefer_card 는 578 교집합)
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
    card_written_blobs += cpatches
    scene_stats[str(HY_LBA)] = {"records": len(pl2882), "mode": "hybrid",
                                "pool_base": HY_BASE, "bins": stats2882,
                                "index_bytes": len(index)}
    share: dict[str, tuple[int, int]] = {}
    for r in pl2882:
        h = r["encoded_hex"]
        bank, addr = loc2882(h)
        if bank < 0x20:
            share[h] = (bank, addr)

    # 578 하이브리드 (b8.3 동일)
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

    # 디스크 패치 + 확장 (b8.3 동일)
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

    # 카드: 씬 테이블(b8.3 동일 4씬) + 텍스트 blob (PoC $20 포함)
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
    # diff 감사: 확장 소스 = 원본 카드 + FF 패딩, 전 512KB 를 선언 범위와 대조
    src_card_ext = CARD_SRC.read_bytes() + b"\xFF" * (CARD_EXT_SIZE - 256 * 1024)
    declared = [(lo, lo + ln) for lo, ln, _ in card_written]
    for i, (x, y) in enumerate(zip(src_card_ext, card)):
        if x != y and not any(s <= i < e for s, e in declared):
            raise ValueError(f"카드 diff 감사 실패 @{i:06X}")
    assert len(card) == CARD_EXT_SIZE

    # 디스어셈블 검산
    for name, addr, length in (("loader", LOADER, len(loader)),
                               ("reader", wnd_reader_addr, len(reader))):
        r = subprocess.run([str(DISASM), "--raw", str(OUT_BIN), f"{addr:X}",
                            f"{eng_off(addr):X}", f"{length:X}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{name} disasm FAIL:\n{r.stdout}\n{r.stderr}")

    manifest = {
        "format": "BTRACK-B9-POC-CARDEXT",
        "runtime_status": "PENDING",
        "changes_vs_b8_3": [
            "card 512KB (b8.3 + FF 256KB — boottest 와 동일 크기, 매직 대신 실 데이터)",
            "scene 482 첫 대사 레코드 1건만 카드 $20:0000(=$A000) 배치 (prefer_card)",
            "그 외 레코드·씬·훅·테이블 = b8.3 동일 (FFD 오프셋만 1레코드 제거로 이동)"],
        "poc": poc_info,
        "scenes": scene_stats,
        "card": {"out": CARD_OUT.name, "size": len(card),
                 "written": [{"off": f"{lo:06X}", "bytes": ln, "what": w}
                             for lo, ln, w in card_written]},
        "window": {"loader": len(loader), "slice": len(wslice),
                   "reader": len(reader), "free": WINDOW_CODE_END - wnd_end},
        "output_bin_sha256": sha256(out),
        "card_sha256": sha256(card),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({"status": "BUILD_OK", "poc": poc_info,
                      "window": manifest["window"],
                      "scenes": {k: v["records"] for k, v in scene_stats.items()},
                      "bin": OUT_BIN.name, "card": CARD_OUT.name,
                      "sha256": manifest["output_bin_sha256"][:16]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
