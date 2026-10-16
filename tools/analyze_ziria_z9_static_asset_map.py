#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z9 — 씬 패키지 정적 자산 지도 (전역 공유 블록 식별 → 뱅크 원천 배제).

배경 (HANDOFF §1 2882 교훈, 2026-08-23):
  씬 RAM cold 는 위치 커버리지 × 상태 커버리지의 곱이다. 아이템 아이콘처럼
  소지 상태에 의존하는 read 는 플레이 CDL 로 전수 관측이 불가능하다.
  이 도구는 그 사각을 정적으로 닫는다.

원리 — 전역 동일 블록 = 엔진 고정 계약 자산:
  96섹터 씬 패키지 전체(32개 고유 LBA)를 같은 씬-상대 오프셋끼리 비교하면,
  "사실상 전 씬에서 바이트 동일"인 블록이 나온다. 엔진이 고정 씬-상대
  주소로 소비하는 자산(아이템 아이콘 타일 등)은 모든 패키지에 같은 위치·
  같은 내용으로 실려야 하므로 이 블록에 속한다. 상태 의존 소비자의 대상도
  여기 있다 → 해당 뱅크는 CDL cold 여부와 무관하게 풀 배치에서 원천 배제.

  반면 2~수 씬 공유(인접 맵 패밀리의 중복 자산)는 배제 사유가 아니다 —
  b7.2 런타임 PASS 뱅크(290 $78 등)가 대량의 쌍 공유를 포함한 채 강화
  게이트를 통과했다. 전역 임계(GLOBAL_MIN_FRACTION)가 이 경계를 가른다.

판정 의미 (fail-closed):
  GLOBAL_ASSET — 전역 공유 바이트 포함 뱅크. 모든 씬에서 풀 배치 금지.
  CDL_HOT     — 그 씬 컨텍스트의 클린 CDL 세그먼트가 접근한 뱅크.
  CANDIDATE   — 정적 배제 사유 없음. **승인이 아니다** — 기존 절차(씬별
                CDL cold + 강화 런타임 게이트)를 통과해야 채택된다.
  잔여 리스크: 씬-고유 상태 의존 소비자(전역 블록 밖)는 이 도구로 못 잡는다.
              게이트에 아이템 획득·메뉴 조작을 유지할 것.

자기검증 (런타임 실측과의 일관성, 위반 시 비정상 종료):
  - b7.1/b7.4 깨짐 뱅크($6C/$6E, $6D/$6F)는 GLOBAL_ASSET 이어야 한다.
  - b7.2 게이트 PASS 채택 뱅크(482 $7B-$7E, 290 $78-$7A/$7E)는
    GLOBAL_ASSET 이 아니어야 한다.
  - 메뉴 CDL 의 $6C/$6E 접근은 전역 블록 내부여야 한다(아이콘=전역 검증).

사용: python -X utf8 tools/analyze_ziria_z9_static_asset_map.py
출력: module_relink/z9_static_asset_map/ (runs TSV + 뱅크 판정 TSV +
      manifest + 전역 블록 타일 렌더 PNG[HITL 판독용]).
분석 전용 — CUE/BIN/ISO 무변경.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MODULE_CATALOG = ROOT / "translation" / "ziria_module_catalog.json"
CDL_DIR = ROOT / "translation" / "cdl"
OUT_DIR = ROOT / "module_relink" / "z9_static_asset_map"

SECTOR = 2048
SCENE_SECTORS = 96
SCENE_BYTES = SCENE_SECTORS * SECTOR          # 0x30000 = bank $68-$7F
BANK_BASE = 0x68
BANK_SIZE = 0x2000
GRAN = 16                                     # 비교 그래뉼 (16B 우연 일치 무시 가능)
NGRAN = SCENE_BYTES // GRAN
GLOBAL_MIN_FRACTION = 0.9                     # 전역 판정: 씬 수 × 0.9 이상 동일
MIN_RUN_BYTES = 64
FILL_BRIDGE_MAX_GRAN = 64                     # run 내부 fill 간극 브리지 상한(1KB)
CONTAMINATION_FRACTION = 0.90                 # Z8.9b 와 동일 기준

# CDL 세그먼트 → 씬 컨텍스트 (2026-08-23 캡처 이력, HANDOFF §1).
# segment_a/b/c 는 Z8.9b 초기 프로토콜 캡처 — segment_b 의 뱅크 지문이
# seg_290_full 과 사실상 일치($6B/$73/$77/$7C)해 마을(290) 플레이 혼입이
# 실측됐다. 혼합 컨텍스트는 씬 귀속 불가 → None (b6/b7 뱅크 선정도
# seg_482_full/menu 만 근거로 했다). segment_c 는 장면 로드 포함(접근 100%)
# — 오염 규칙이 자동 제외하지만 명시도 해 둔다.
CDL_SCENE_CONTEXT: dict[str, int | None] = {
    "seg_482_full.cdl": 482, "seg_482_menu.cdl": 482,
    "segment_a.cdl": None, "segment_b.cdl": None,
    "seg_290_full.cdl": 290, "seg_290_menu.cdl": 290,
    # ⚠ 정정(2026-08-23 심야): 두 번째 마을의 실제 씬 = overlay LBA 578
    # ×78섹터 (비-96 씬 클래스). town2 캡처는 578 컨텍스트 증거다 —
    # 290 귀속은 오판이었다 (96섹터 필터가 모집단을 잘랐던 것이 원인).
    # 이 도구의 씬 모집단이 96섹터 한정인 동안 578 은 판정에 미사용.
    "seg_290_town2.cdl": 578,
    "seg_2882_full.cdl": 2882, "seg_2882_tower.cdl": 2882,
    "segment_c.cdl": None,
}

# rich 캡처 소실 씬의 동결 CDL hot 뱅크 (bank 단위 —
# manifest_2026-08-23_rich_cdl_frozen.json, 사고 기록은 Z9_b8 문서 §5).
# 원본 rich 캡처(482/290/2882 _full)가 얇은 재캡처로 덮여 소실됐으므로,
# 현존 세그먼트 union 에 이 집합을 항상 합산한다 (없으면 후보 과대).
FROZEN_CDL_HOT: dict[int, set[int]] = {
    482: {0x6A, 0x6B, 0x70, 0x71, 0x74, 0x75, 0x76, 0x77,
          0x78, 0x79, 0x7A, 0x7F},
    290: {0x6A, 0x6B, 0x70, 0x71, 0x74, 0x75, 0x77, 0x7B, 0x7C, 0x7D},
    2882: {0x6A, 0x6B, 0x70, 0x71, 0x74, 0x75, 0x76, 0x77,
           0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D},
}

# 런타임 실측 앵커 (자기검증용 — HANDOFF §1):
# b7.1: 메뉴 장비 아이콘 깨짐 ← 풀이 $6C/$6E 침범.
# b7.4: 탑 신규 획득 아이템 아이콘 깨짐 ← 풀이 $6D/$6F 침범.
RUNTIME_FAIL_BANKS = {0x6C, 0x6E, 0x6D, 0x6F}
# b7.2: 강화 게이트 전 항목 PASS (사용자 실플레이) — 채택 뱅크.
# 290 이력(2026-08-23 심야 정정): town2 CDL 을 290 에 오귀속해 $78-$7A 를
# 한때 무효 판정했으나, town2 의 실제 씬은 578(비-96) — 오귀속 철회.
# 다만 현행 기준 빌드 b8.1 은 이미 {76,7F,7E} 로 재선정돼 있고 이는 양쪽
# 해석 모두에서 안전한 부분집합. 앵커는 보수적으로 $7E 만 유지.
RUNTIME_PASS_BANKS = {482: {0x7B, 0x7C, 0x7D, 0x7E},
                      290: {0x7E}}

# 전역 블록 주석 (씬-상대 오프셋 기준, 이 도구의 최초 실행에서 판독):
# 0xC000..0x10000 은 그레이스케일 타일 렌더로 아이템 아이콘(무기·방어구·
# 소모품 등 16x16, 4타일×32B)임을 시각 판독 — renders/ PNG 가 증거.
ANNOTATIONS = [
    (0x0000, 0x28A0, "씬 부트스트랩 코드+고정 테이블 (482 의 JSR $E009 @0xA01 포함)"),
    (0x8000, 0xBB00, "공유 자산 A — 노이즈성(압축 추정), 메뉴가 head 0x8000..0x94A0 소비(CDL)"),
    (0xC000, 0x10000, "아이템 아이콘 타일 블록 (raw PCE 타일, 렌더 판독 — b7.1/b7.4 깨짐의 원천)"),
    (0x15A00, 0x16EE0, "공유 자산 B — 노이즈성(용도 미상)"),
]


def fail(msg: str):
    print(f"FAIL: {msg}")
    sys.exit(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


# ---- CDL (BizHawk PCE) — Z8.9b 파서와 동일 형식 -----------------------------

def read_7bit_string(f) -> str:
    length = 0
    shift = 0
    while True:
        b = f.read(1)
        if not b:
            fail("CDL 문자열 헤더 EOF")
        v = b[0]
        length |= (v & 0x7F) << shift
        if not v & 0x80:
            break
        shift += 7
    return f.read(length).decode("utf-8")


def parse_cdl(path: Path) -> bytes | None:
    with path.open("rb") as fh:
        f = io.BufferedReader(fh)
        magic = read_7bit_string(f)
        if magic == "BIZHAWK-CDL-2":
            subtype = read_7bit_string(f).rstrip(" ")
        elif magic == "BIZHAWK-CDL-1":
            subtype = "PCE"
        else:
            fail(f"{path.name}: BizHawk CDL 아님 (magic {magic!r})")
        if subtype != "PCE":
            fail(f"{path.name}: CDL subtype {subtype!r} != PCE")
        (count,) = struct.unpack("<i", f.read(4))
        blocks = {}
        for _ in range(count):
            key = read_7bit_string(f)
            (ln,) = struct.unpack("<i", f.read(4))
            blocks[key] = f.read(ln)
    data = blocks.get("Super System Card RAM")
    if data is None:
        fail(f"{path.name}: 'Super System Card RAM' 블록 없음")
    if len(data) != SCENE_BYTES:
        fail(f"{path.name}: 블록 크기 {len(data):#x} != {SCENE_BYTES:#x}")
    return data


# ---- 타일 렌더 (HITL 판독용, PIL 없으면 생략) --------------------------------

def render_run(data: bytes, out_png: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    tiles_per_row = 32
    ntiles = len(data) // 32
    rows = (ntiles + tiles_per_row - 1) // tiles_per_row
    img = Image.new("RGB", (tiles_per_row * 8, max(rows, 1) * 8), (32, 32, 64))
    for t in range(ntiles):
        d = data[t * 32:(t + 1) * 32]
        tx, ty = (t % tiles_per_row) * 8, (t // tiles_per_row) * 8
        for y in range(8):
            p0, p1 = d[y * 2], d[y * 2 + 1]
            p2, p3 = d[16 + y * 2], d[16 + y * 2 + 1]
            for x in range(8):
                bit = 7 - x
                v = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1) | \
                    (((p2 >> bit) & 1) << 2) | (((p3 >> bit) & 1) << 3)
                img.putpixel((tx + x, ty + y), (17 * v, 17 * v, 17 * v))
    img.resize((img.width * 2, img.height * 2)).save(out_png)
    return True


def banks_of(start: int, end: int) -> str:
    b0 = BANK_BASE + start // BANK_SIZE
    b1 = BANK_BASE + (end - 1) // BANK_SIZE
    return f"${b0:02X}" if b0 == b1 else f"${b0:02X}..${b1:02X}"


def main() -> None:
    if not ISO.is_file():
        fail("extracted_bin/Track02_data.iso 없음 — python tools/extract_bin.py 먼저")
    iso = ISO.read_bytes()
    catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))
    entries = catalog["directories"]["overlay"]["entries"]
    lbas = sorted({e["lba"] for e in entries
                   if e["sector_count"] == SCENE_SECTORS})
    if len(lbas) < 16:
        fail(f"96섹터 씬 패키지 {len(lbas)}개 — 모집단 이상 (카탈로그 확인)")
    for lba in lbas:
        if (lba + SCENE_SECTORS) * SECTOR > len(iso):
            fail(f"scene {lba}: extent 가 ISO 밖")
    pkgs = {lba: iso[lba * SECTOR: lba * SECTOR + SCENE_BYTES] for lba in lbas}
    n = len(lbas)
    global_thresh = max(2, math.ceil(n * GLOBAL_MIN_FRACTION))

    # ---- 그래뉼별 공유 그룹 크기 -------------------------------------------
    # share_max[g]   = 최대 동일값 그룹 크기 (전 씬)
    # share_scene[lba][g] = 그 씬의 값이 속한 그룹 크기 (씬별 경고용)
    share_max = [0] * NGRAN
    is_fill = bytearray(NGRAN)      # 전 씬에서 "단일 반복 바이트" 값만 나타남
    global_gran = bytearray(NGRAN)  # 전역 공유 (비-fill, group >= 임계)
    share_scene = {lba: [0] * NGRAN for lba in lbas}
    for g in range(NGRAN):
        o = g * GRAN
        groups: Counter[bytes] = Counter()
        for lba in lbas:
            groups[pkgs[lba][o:o + GRAN]] += 1
        mx_val, mx = max(groups.items(), key=lambda kv: kv[1])
        share_max[g] = mx
        for lba in lbas:
            share_scene[lba][g] = groups[pkgs[lba][o:o + GRAN]]
        if all(len(set(v)) == 1 for v in groups):
            is_fill[g] = 1
        elif mx >= global_thresh and len(set(mx_val)) > 1:
            global_gran[g] = 1

    # ---- 전역 run 병합 (fill 간극 브리지 — 배제를 넓히는 방향) --------------
    runs: list[tuple[int, int, int]] = []   # (start_gran, end_gran, bridged)
    g = 0
    while g < NGRAN:
        if not global_gran[g]:
            g += 1
            continue
        s = g
        bridged = 0
        e = g + 1
        while e < NGRAN:
            if global_gran[e]:
                e += 1
                continue
            j = e
            while j < NGRAN and is_fill[j] and not global_gran[j]:
                j += 1
            if (j < NGRAN and global_gran[j]
                    and j - e <= FILL_BRIDGE_MAX_GRAN):
                bridged += j - e
                e = j + 1
            else:
                break
        runs.append((s, e, bridged))
        g = e
    runs = [(s * GRAN, e * GRAN, br * GRAN) for s, e, br in runs
            if (e - s) * GRAN >= MIN_RUN_BYTES]

    # ---- CDL 로드·분류 ------------------------------------------------------
    cdl_by_scene: dict[int, dict[str, bytes]] = {}
    cdl_report = []
    for p in sorted(CDL_DIR.glob("*.cdl")):
        if p.name not in CDL_SCENE_CONTEXT:
            fail(f"CDL {p.name}: 씬 컨텍스트 미등록 — CDL_SCENE_CONTEXT 에 추가")
        ctx = CDL_SCENE_CONTEXT[p.name]
        data = parse_cdl(p)
        touched = sum(1 for b in data if b)
        frac = touched / SCENE_BYTES
        row = {"file": p.name, "scene_context": ctx,
               "touched_fraction": round(frac, 4)}
        if ctx is None:
            row["status"] = "EXCLUDED_BY_TABLE"
        elif frac > CONTAMINATION_FRACTION:
            row["status"] = "EXCLUDED_CONTAMINATED"
        elif touched == 0:
            row["status"] = "EXCLUDED_EMPTY"
        else:
            row["status"] = "OK"
            cdl_by_scene.setdefault(ctx, {})[p.name] = data
        cdl_report.append(row)

    def scene_hot_banks(lba: int) -> dict[int, int]:
        """씬 컨텍스트 클린 세그먼트 union 의 뱅크별 접근 바이트 수."""
        out: dict[int, int] = {}
        segs = cdl_by_scene.get(lba, {})
        if not segs:
            return out
        for b in range(24):
            s, e = b * BANK_SIZE, (b + 1) * BANK_SIZE
            cnt = sum(1 for i in range(s, e)
                      if any(seg[i] for seg in segs.values()))
            if cnt:
                out[BANK_BASE + b] = cnt
        return out

    # ---- 뱅크 판정 ----------------------------------------------------------
    global_bank_bytes: dict[int, int] = {}
    for g in range(NGRAN):
        if global_gran[g]:
            bank = BANK_BASE + (g * GRAN) // BANK_SIZE
            global_bank_bytes[bank] = global_bank_bytes.get(bank, 0) + GRAN
    global_banks = set(global_bank_bytes)

    verdict_rows = []
    scene_verdicts = {}
    for lba in lbas:
        hot = scene_hot_banks(lba)
        frozen = FROZEN_CDL_HOT.get(lba, set())
        has_cdl = lba in cdl_by_scene or bool(frozen)
        banks = {}
        candidates = []
        for b in range(BANK_BASE, BANK_BASE + 24):
            if b in global_banks:
                v = "GLOBAL_ASSET"
                detail = f"전역 공유 {global_bank_bytes[b]}B"
            elif b in hot or b in frozen:
                v = "CDL_HOT"
                srcs = list(cdl_by_scene.get(lba, {}))
                if b in frozen:
                    srcs.append("frozen_2026-08-23")
                detail = f"접근 {hot.get(b, 0)}B ({', '.join(srcs)})"
            else:
                v = "CANDIDATE" if has_cdl else "CANDIDATE_STATIC_ONLY"
                warn_b = sum(GRAN for g in range((b - BANK_BASE) * BANK_SIZE // GRAN,
                                                 (b - BANK_BASE + 1) * BANK_SIZE // GRAN)
                             if not is_fill[g] and share_scene[lba][g] >= 8)
                detail = (f"패밀리 공유(g>=8) {warn_b}B — 게이트 필수" if warn_b
                          else ("씬 CDL 미보유 — cold 검증 필요" if not has_cdl
                                else ""))
                candidates.append(b)
            banks[f"{b:02X}"] = {"verdict": v, "detail": detail}
            verdict_rows.append((lba, b, v, detail))
        scene_verdicts[str(lba)] = {
            "cdl_segments": sorted(cdl_by_scene.get(lba, {})),
            "candidate_banks": [f"{b:02X}" for b in candidates],
            "banks": banks,
        }

    # ---- 자기검증 (런타임 실측 일관성 — fail-closed) ------------------------
    checks = []

    def check(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            fail(f"자기검증 실패 [{name}]: {detail}")

    check("runtime_fail_banks_are_global",
          RUNTIME_FAIL_BANKS <= global_banks,
          f"b7.1/b7.4 깨짐 뱅크 {sorted(f'{b:02X}' for b in RUNTIME_FAIL_BANKS)}"
          f" ⊆ 전역 {sorted(f'{b:02X}' for b in global_banks)}")
    for lba, banks_ in RUNTIME_PASS_BANKS.items():
        check(f"runtime_pass_banks_not_global_{lba}",
              not (banks_ & global_banks),
              f"b7.2 PASS 뱅크 {sorted(f'{b:02X}' for b in banks_)} 전역과 교집합 없음")
        # 채택 뱅크는 CANDIDATE 여야 한다 — CDL 세그먼트 씬 오귀속(혼합
        # 컨텍스트를 특정 씬에 배정)을 잡는 가드.
        bad = [f"{b:02X}" for b in banks_
               if scene_verdicts[str(lba)]["banks"][f"{b:02X}"]["verdict"]
               != "CANDIDATE"]
        check(f"runtime_pass_banks_are_candidates_{lba}",
              not bad,
              f"b7.2 PASS 뱅크 중 비-CANDIDATE {bad or '없음'}")
    # 메뉴 CDL 의 $6C/$6E 접근 = 전역 블록 내부 (아이콘·공유자산 소비 검증)
    menu_segs = [d for s in (482, 290)
                 for f_, d in cdl_by_scene.get(s, {}).items() if "menu" in f_]
    if menu_segs:
        inside = outside = 0
        run_set = [(s, e) for s, e, _ in runs]
        for b in (0x6C, 0x6E):
            s0, e0 = (b - BANK_BASE) * BANK_SIZE, (b - BANK_BASE + 1) * BANK_SIZE
            for i in range(s0, e0):
                if any(seg[i] for seg in menu_segs):
                    if any(s <= i < e for s, e in run_set):
                        inside += 1
                    else:
                        outside += 1
        check("menu_cdl_icon_access_inside_global_runs",
              outside == 0 and inside > 0,
              f"$6C/$6E 메뉴 접근 {inside}B 전역 블록 내부, 외부 {outside}B")
    # 482 부트스트랩 JSR $E009 @0xA01 이 전역 블록 안에서 전 씬 동일
    boot = pkgs[482][0xA01:0xA04]
    check("bootstrap_jsr_e009_global",
          boot == bytes((0x20, 0x09, 0xE0))
          and all(pkgs[l][0xA01:0xA04] == boot for l in lbas)
          and any(s <= 0xA01 < e for s, e, _ in runs),
          "0xA01 JSR $E009 전 씬 동일 + 전역 run 내부")

    # ---- 페이로드 대비 용량 사전점검 (참고 수치 — 승인 아님) ----------------
    capacity = {}
    for lba in lbas:
        name = ("btrack_b4_field_payload.json" if lba == 482
                else f"btrack_b7_scene_{lba}_payload.json")
        p = ROOT / "translation" / name
        if not p.exists():
            continue
        recs = json.loads(p.read_text(encoding="utf-8"))["records"]
        text_need = sum(len(r["encoded_hex"]) // 2 for r in recs)
        index_est = 2 + 48 + 7 * len(recs) + 24 + 0x100   # 인덱스+armchk 근사
        cand = scene_verdicts[str(lba)]["candidate_banks"]
        cap = len(cand) * BANK_SIZE
        capacity[str(lba)] = {
            "records": len(recs), "text_bytes": text_need,
            "index_est_bytes": index_est,
            "candidate_banks": cand, "candidate_capacity": cap,
            "ram_only_feasible": text_need + index_est <= cap,
        }

    # ---- 출력 ---------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rendered = []
    run_rows = []
    for s, e, br in runs:
        note = ""
        for a0, a1, txt in ANNOTATIONS:
            if max(s, a0) < min(e, a1):
                note = txt
                break
        png = OUT_DIR / "renders" / f"run_{s:06X}.png"
        png.parent.mkdir(exist_ok=True)
        if render_run(pkgs[482][s:e], png):
            rendered.append(png.name)
        run_rows.append({
            "offset_start": f"{s:06X}", "offset_end": f"{e:06X}",
            "bytes": e - s, "banks": banks_of(s, e),
            "fill_bridged_bytes": br, "annotation": note,
        })
    runs_tsv = OUT_DIR / "global_asset_runs.tsv"
    with runs_tsv.open("w", encoding="utf-8", newline="\n") as f:
        f.write("offset_start\toffset_end\tbytes\tbanks\tfill_bridged_bytes\tannotation\n")
        for r in run_rows:
            f.write("\t".join(str(r[k]) for k in
                    ("offset_start", "offset_end", "bytes", "banks",
                     "fill_bridged_bytes", "annotation")) + "\n")
    verdict_tsv = OUT_DIR / "bank_verdicts.tsv"
    with verdict_tsv.open("w", encoding="utf-8", newline="\n") as f:
        f.write("scene_lba\tbank\tverdict\tdetail\n")
        for lba, b, v, d in verdict_rows:
            f.write(f"{lba}\t{b:02X}\t{v}\t{d}\n")

    manifest = {
        "format": "ZIRIA-Z9-STATIC-ASSET-MAP",
        "version": 1,
        "iso_sha256": sha256(ISO),
        "scene_population": {"unique_96sector_lbas": n, "lbas": lbas},
        "rules": {
            "granule_bytes": GRAN,
            "global_min_fraction": GLOBAL_MIN_FRACTION,
            "global_threshold_scenes": global_thresh,
            "fill_definition": "그래뉼 16B 가 전 씬에서 단일 반복 바이트",
            "min_run_bytes": MIN_RUN_BYTES,
            "fill_bridge_max_bytes": FILL_BRIDGE_MAX_GRAN * GRAN,
            "meaning": "GLOBAL_ASSET 뱅크는 전 씬 풀 배치 금지. CANDIDATE 는"
                       " 승인이 아니라 '정적 배제 사유 없음' — 씬별 CDL cold"
                       " + 강화 게이트가 여전히 필요하다.",
            "residual_risk": "씬-고유 상태 의존 소비자는 미검출 — 게이트에"
                             " 아이템 획득·메뉴 조작 포함 필수",
        },
        "global_asset_runs": run_rows,
        "global_bank_bytes": {f"{b:02X}": v
                              for b, v in sorted(global_bank_bytes.items())},
        "excluded_banks_all_scenes": sorted(f"{b:02X}" for b in global_banks),
        "cdl_segments": cdl_report,
        "self_checks": checks,
        "scene_verdicts": scene_verdicts,
        "capacity_precheck": capacity,
        "renders": rendered,
        "status": "PASS",
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "scenes": n,
        "global_threshold": f">={global_thresh}/{n}",
        "excluded_banks_all_scenes": manifest["excluded_banks_all_scenes"],
        "global_runs": [(r["offset_start"], r["offset_end"], r["banks"])
                        for r in run_rows],
        "self_checks": [(c["check"], c["ok"]) for c in checks],
        "capacity_precheck": {k: {"text": v["text_bytes"],
                                  "cap": v["candidate_capacity"],
                                  "ram_only": v["ram_only_feasible"],
                                  "banks": v["candidate_banks"]}
                              for k, v in capacity.items()},
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
