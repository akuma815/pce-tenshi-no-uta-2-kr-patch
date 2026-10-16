#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z9 — 씬 파라미터화 dialogue 참조·bytecode 분모 분석 (필드 Z8.2+Z8.5 일반화).

사용: python tools/analyze_ziria_z9_scene_refs.py <scene_lba> [<scene_lba> ...]

필드(482) 도구와의 차이:
  - 씬 LBA 인자화. 로더 디렉터리에서 lba×96 엔트리 정확히 1개를 요구(동일).
  - 런타임 trace 보강 생략 (필드 코스 한정 증거라 타 씬에 무의미).
  - Memo 포인터/부분 인라인/오탐 등 필드 특수 케이스를 전제하지 않는다.
    선행 바이트가 02/03/14 가 아닌 행은 **전건 수집 후 UNCLASSIFIED 로 보고
    하고 비정상 종료** — 씬별 경계 케이스의 발견 절차다 (fail-closed).
  - kind/boundary 분포는 필드 상수와 대조하지 않고 manifest 에 보고한다.

출력: module_relink/z9_scene_refs/scene_<lba>/ 아래 catalog + manifest.
분석 전용 — CUE/BIN/ISO 무변경.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MODULE_CATALOG = ROOT / "translation" / "ziria_module_catalog.json"
OUT_BASE = ROOT / "module_relink" / "z9_scene_refs"

SECTOR = 2048
SCENE_SECTORS = 96
BANK_BASE = 0x68
INLINE_OPCODES = (0x02, 0x03, 0x14)

# 씬별 명시 제외 (2026-08-23 triage — 근거는 각 항목 주석과 HANDOFF §1):
# STRING_TABLE_MEMBER: 짧은 NUL 문자열 연속 블록의 멤버 — 인라인 이벤트 대사가
#   아니라 별도 소비자(이름/명칭 테이블). 대사 리다이렉트 부적격.
# SUSPECT_DATA_TABLE: 주변이 구조화 데이터 패턴(EF 00 .. FF 류) — master 추출
#   오탐 의심. fail-closed 로 원문 유지(최악=일본어 잔존, 비파괴).
# 2026-08-23 전 씬 triage (68행): 단독 잔여 14행은 전건 육안 검토 —
#   LE16 포인터/타일열(1154·1922·2690·3074@2E878·3362@2E30F·5282@2E443),
#   반각·정렬 깨진 데이터(그 외). 반복 구조는 아래 구조 검출기가 담당.
SCENE_OVERRIDES: dict[int, dict[str, str]] = {
    # 482 의 2행은 Z8.6 boundary-repair 가 소유 (482 빌드 입력은 b4 페이로드
    # — z9 카탈로그는 482 에 한해 정보 제공용).
    482: {"iso:010CAE1": "Z8_PIPELINE_HANDLED",
          "iso:010D080": "Z8_PIPELINE_HANDLED"},
    2882: {
        "iso:05B12E1": "SUSPECT_DATA_TABLE",
        "iso:05B1712": "SUSPECT_DATA_TABLE",
        "iso:05B3E56": "STRING_TABLE_MEMBER",
        "iso:05B3EC0": "STRING_TABLE_MEMBER",
    },
    1154: {"iso:0251700": "SUSPECT_DATA_TABLE"},
    1250: {"iso:02A08AD": "SUSPECT_DATA_TABLE"},
    1922: {"iso:03DF8D8": "SUSPECT_DATA_TABLE",
           "iso:03DF928": "SUSPECT_DATA_TABLE"},
    2690: {"iso:055F768": "SUSPECT_DATA_TABLE",
           "iso:055F828": "SUSPECT_DATA_TABLE",
           "iso:055F88F": "SUSPECT_DATA_TABLE",
           "iso:055F8D1": "SUSPECT_DATA_TABLE"},
    3074: {"iso:062F878": "SUSPECT_DATA_TABLE",
           "iso:062F8BF": "SUSPECT_DATA_TABLE"},
    3362: {"iso:06BF30F": "SUSPECT_DATA_TABLE",
           "iso:06BF36C": "SUSPECT_DATA_TABLE"},
    3458: {"iso:06D1B26": "SUSPECT_DATA_TABLE"},
    3842: {"iso:07AFD3F": "SUSPECT_DATA_TABLE"},
    # 4226 뒤 2행: +0x400 보폭 동일 본문 사본인데 선행 8B 첫 바이트만 달라
    # (40 vs 00) dup 검출기 미적중 — 육안 판정으로 명시 제외.
    4226: {"iso:08511AA": "SUSPECT_DATA_TABLE",
           "iso:0851DA5": "SUSPECT_DATA_TABLE",
           "iso:08521A5": "SUSPECT_DATA_TABLE"},
    5282: {"iso:0A7F443": "SUSPECT_DATA_TABLE"},
    # 2026-08-28 비96섹터 21씬 triage (12행 육안 검토, b9 편입 준비):
    # 11행 = LE16 타일 쿼드/반복 필 데이터 (52xx·31xx·32xx 연속쌍 —
    # 예: 52D4 52D5 / 52E4 52E5 는 2x2 메타타일). 전건 pre/post 도 동일 패턴.
    1538: {"iso:031F96F": "SUSPECT_DATA_TABLE"},
    1730: {"iso:037F7FF": "SUSPECT_DATA_TABLE",
           "iso:037F9E0": "SUSPECT_DATA_TABLE"},   # 타일열+텍스트 파편 혼합
    2498: {"iso:04FF977": "SUSPECT_DATA_TABLE"},
    2594: {"iso:052F7AF": "SUSPECT_DATA_TABLE"},
    4706: {"iso:0954633": "SUSPECT_DATA_TABLE"},
    4898: {"iso:09AF440": "SUSPECT_DATA_TABLE",
           "iso:09AF6AC": "SUSPECT_DATA_TABLE"},
    4994: {"iso:09E658C": "SUSPECT_DATA_TABLE"},
    5090: {"iso:0A01F0C": "SUSPECT_DATA_TABLE",
           "iso:0A0F65F": "SUSPECT_DATA_TABLE"},
    # 1행 = 실제 대사 텍스트(항해 인사말, ISO 전체에서 유일 출현)인데
    # 선행 바이트 00 — inline opcode 참조 없음(연속 스트림/이벤트 테이블
    # 참조 추정). fail-closed 원문 유지, QA 플레이스루에서 일본어로 보이면
    # 그때 소비자 규명 (HANDOFF §1 미번역 잔존 triage 경로).
    2114: {"iso:043B88A": "UNRESOLVED_CONSUMER_TEXT"},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def u24le(v: int) -> str:
    return v.to_bytes(3, "little").hex().upper()


def analyze_scene(lba: int, iso: bytes, master_rows: list[dict],
                  module_catalog: dict) -> dict:
    overlay = module_catalog["directories"]["overlay"]
    # 씬 = overlay 디렉터리 엔트리 (섹터수는 실측 — 96 고정 아님, 2026-08-23
    # 심야 정정: 69~94섹터 씬 23개 존재. 동일 (lba,count) 중복 엔트리 허용
    # — 1730×92 가 2회 등재돼 있음).
    matches = {(e["lba"], e["sector_count"], e["raw_hex"])
               for e in overlay["entries"] if e["lba"] == lba}
    if len(matches) != 1:
        raise ValueError(f"scene {lba}: loader entry {len(matches)}종 (1종 필요)")
    (_, sectors, raw_hex), = matches
    raw4 = bytes.fromhex(raw_hex)
    if (int.from_bytes(raw4[:3], "big"), raw4[3]) != (lba, sectors):
        raise ValueError(f"scene {lba}: loader raw 디코드 불일치")

    start = lba * SECTOR
    end = start + sectors * SECTOR

    selected = [r for r in master_rows
                if r["category"] == "dialogue"
                and start <= int(r["iso_offset"], 16) < end]

    # ---- Memo 포인터 블록 탐지 (필드 Z8.5 일반화) --------------------------
    # 패턴: LE u16 포인터열(값 C000..C3FF, 3개+)이 테이블, base = table-0x10.
    # 각 포인터의 타깃 = base + (ptr-0xC000) 은 씬 내 NUL 종료 레코드여야 한다.
    memo_targets: dict[int, tuple[int, int]] = {}   # target_off -> (storage, ptr)
    memo_table_rows: set[str] = set()
    sel_by_off = {int(r["iso_offset"], 16): r for r in selected}
    for r in selected:
        off = int(r["iso_offset"], 16)
        raw = bytes.fromhex(r["raw_hex"])
        # 행 시작 직전 바이트까지 포함해 u16 정렬 후보 두 위치를 시도
        for t in (off - 1, off):
            ptrs = []
            p = t
            while p + 1 < end:
                v = iso[p] | (iso[p + 1] << 8)
                if 0xC000 <= v < 0xC400:
                    ptrs.append((p, v))
                    p += 2
                else:
                    break
            if len(ptrs) >= 3:
                base = t - 0x10
                ok = True
                for storage, v in ptrs:
                    tgt = base + (v - 0xC000)
                    if not (start <= tgt < end) or 0 not in iso[tgt:tgt + 256]:
                        ok = False
                        break
                if ok:
                    memo_table_rows.add(r["id"])
                    for storage, v in ptrs:
                        memo_targets[base + (v - 0xC000)] = (storage, v)
                    break

    def is_table_data(raw: bytes, off: int) -> bool:
        """저바이트 전용 + (준)순차/제로패딩 문맥 = 텍스트 아님 (가나 테이블류)."""
        body = raw[:-1]
        if not body or any(b >= 0x80 for b in body):
            return False
        zeros_before = iso[off - 3:off] == b"\x00\x00\x00"
        asc = sum(1 for a, b in zip(body, body[1:]) if b >= a)
        seqish = len(body) > 1 and asc / (len(body) - 1) >= 0.8
        return zeros_before or seqish

    # ---- 구조 검출기 (2026-08-23 전 씬 triage 68행 일반화) -----------------
    # 이벤트 대사는 씬 내에서 유일하고 씬마다 내용·문맥이 다르다. 반대 증거가
    # 있으면 데이터 구조로 판정해 fail-closed 제외한다 (원문 유지, 비파괴).
    all_scenes = sorted({(e["lba"], e["sector_count"])
                         for e in overlay["entries"]})

    def dup_in_scene(off: int, raw: bytes) -> bool:
        """씬 패키지 안에 선행 8B+본문 동일 사본이 2개 이상 = 보폭 복제 데이터
        (실측: ±0x400/0x800/0x2000/0x4000 보폭 사본 — 962·5186·5282 등)."""
        if off - 8 < start:
            return False
        pat = iso[off - 8:off] + raw
        return iso[start:end].count(pat) >= 2

    def cross_scene_fixed(off: int) -> bool:
        """같은 씬-상대 오프셋에 동일 선행 8B 를 가진 씬이 3개 이상 = 고정
        구조 슬롯 (실측: rel 0x12E56 이름테이블 ×11씬, rel 0x1802E ×7씬 등)."""
        rel_off = off - start
        if rel_off < 8:
            return False
        prev = iso[off - 8:off]
        n = sum(1 for l, sc in all_scenes
                if rel_off < sc * SECTOR
                and iso[l * SECTOR + rel_off - 8: l * SECTOR + rel_off] == prev)
        return n >= 3

    catalog = []
    kinds: Counter[str] = Counter()
    unclassified = []
    for r in selected:
        off = int(r["iso_offset"], 16)
        raw = bytes.fromhex(r["raw_hex"])
        if iso[off:off + len(raw)] != raw or raw[-1] != 0:
            raise ValueError(f"{r['id']}: 보호 원문 불일치/터미네이터 없음")
        if off + len(raw) > end:
            raise ValueError(f"{r['id']}: 레코드가 씬 끝을 넘음")
        rel = off - start
        opcode = iso[off - 1]
        if r["id"] in SCENE_OVERRIDES.get(lba, {}):
            kind = SCENE_OVERRIDES[lba][r["id"]]
        elif r["id"] in memo_table_rows:
            kind = "MEMO_TABLE_ROW"          # 테이블 자체가 행으로 추출된 것 — 제외
        elif off in memo_targets:
            kind = "MEMO_POINTER_TARGET"     # 포인터 참조 레코드 — redirect 대상
        elif opcode in INLINE_OPCODES:
            kind = f"INLINE_OPCODE_{opcode:02X}"
        elif is_table_data(raw, off):
            kind = "FALSE_POSITIVE_TABLE"    # 저바이트 순차/패딩 문맥 — 제외
        elif dup_in_scene(off, raw):
            kind = "DUPLICATE_STRIDED_COPY"  # 씬 내 동일 사본 — 데이터, 제외
        elif cross_scene_fixed(off):
            kind = "CROSS_SCENE_FIXED_STRUCTURE"  # 씬 간 고정 구조 — 제외
        else:
            kind = "UNCLASSIFIED"
            unclassified.append({
                "id": r["id"], "iso_offset": f"0x{off:07X}",
                "preceding_bytes": iso[max(0, off - 8):off].hex().upper(),
                "head": raw[:12].hex().upper(),
            })
        kinds[kind] += 1
        catalog.append({
            "id": r["id"],
            "source_iso_offset": f"0x{off:07X}",
            "source_module_offset": f"0x{rel:05X}",
            "source_key_u24le": u24le(rel),
            "source_physical_bank": f"0x{BANK_BASE + rel // 8192:02X}",
            "raw_length": len(raw),
            "reference_kind": kind,
            "reference_raw_hex": f"{opcode:02X}" if kind != "UNCLASSIFIED" else "",
            "subcategory": r["subcategory"],
        })

    out_dir = OUT_BASE / f"scene_{lba}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cat_path = out_dir / "dialogue_reference_catalog.csv"
    with cat_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(catalog[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(catalog)
    uncls_path = out_dir / "unclassified_rows.csv"
    if unclassified:
        with uncls_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(unclassified[0].keys()),
                               lineterminator="\n")
            w.writeheader()
            w.writerows(unclassified)
    elif uncls_path.exists():
        uncls_path.unlink()          # 이전 실행 잔재 제거 (stale triage 방지)

    manifest = {
        "format": "ZIRIA-Z9-SCENE-DIALOGUE-REFS",
        "version": 1,
        "scene_lba": lba,
        "sector_count": sectors,
        "loader_reference": {"raw_hex": raw4.hex().upper(), "status": "PASS"},
        "records": len(catalog),
        "reference_kinds": dict(kinds),
        "unclassified": len(unclassified),
        "status": ("PASS" if not unclassified
                   else "FAIL_UNCLASSIFIED_ROWS_REQUIRE_TRIAGE"),
        "catalog_sha256": sha256(cat_path),
        "note": "trace 보강·boundary repair 는 씬별 후속 단계 (필드 Z8.4/8.6 대응)",
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main() -> None:
    lbas = [int(a) for a in sys.argv[1:]]
    if not lbas:
        raise SystemExit("사용: analyze_ziria_z9_scene_refs.py <scene_lba> ...")
    iso = ISO.read_bytes()
    master_rows = list(csv.DictReader(
        MASTER.open(encoding="utf-8-sig", newline="")))
    module_catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))

    results = []
    for lba in lbas:
        m = analyze_scene(lba, iso, master_rows, module_catalog)
        results.append(m)
        print(json.dumps({k: m[k] for k in
                          ("scene_lba", "records", "reference_kinds",
                           "unclassified", "status")},
                         ensure_ascii=False))
    if any(m["status"] != "PASS" for m in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
