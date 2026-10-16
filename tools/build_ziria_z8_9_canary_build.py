#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9 canary 진단 빌드 생성기.

Z8.9c 배치 시뮬레이션이 선택한 scene RAM cold 구간(canary_fill_ranges.tsv)을
트랩 패턴 `00 E7` 반복으로 채운 진단 BIN/CUE를 만든다.

의미: 이 구간들이 정말로 field 장면 수명 동안 CPU가 접근하지 않는다면
게임은 원본과 완전히 동일하게 동작해야 한다. 접근이 있다면
BRK(`EXEC BRK`), 화면 깨짐, 진행 이상으로 즉시 드러난다.

fail-closed:
- 원본 BIN 전체 SHA-256 검사 후에만 진행
- 기록 후 Track02 슬라이스를 전수 재검증: 계획된 바이트만 다르고
  나머지는 원본과 동일해야 한다
- 계획/실측 diff 불일치 시 산출물을 삭제하고 종료 코드 1

산출물(진단 전용, 릴리스 입력 금지):
  Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9_canary.bin/.cue
  translation/ziria_z8_9_canary_build_manifest.json
"""

import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
CUE_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue")
BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
TRACK02_OFFSET = 7914480
TRACK02_SECTORS = 9328
SCENE_ISO_BASE = 0xF1000          # LBA 482 * 2048

RANGES_TSV = os.path.join(ROOT, "module_relink", "z8_9_wire_v2", "canary_fill_ranges.tsv")
OUT_BIN = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9_canary.bin")
OUT_CUE = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9_canary.cue")
OUT_MANIFEST = os.path.join(ROOT, "translation", "ziria_z8_9_canary_build_manifest.json")

PATTERN = bytes([0x00, 0xE7])


def fail(msg):
    for p in (OUT_BIN, OUT_CUE):
        if os.path.isfile(p):
            os.remove(p)
    print(f"FAIL: {msg}")
    sys.exit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            c = f.read(1 << 22)
            if not c:
                break
            h.update(c)
    return h.hexdigest().upper()


def main():
    print("checking original BIN hash...")
    if sha256_file(BIN_PATH) != BIN_SHA256:
        print("FAIL: original BIN hash mismatch")
        sys.exit(1)

    ranges = []
    with open(RANGES_TSV, "r", encoding="utf-8") as f:
        f.readline()
        for ln in f.read().splitlines():
            s, e, _b = ln.split("\t")
            s, e = int(s, 16), int(e, 16)
            if not (0 <= s < e <= 0x30000):
                fail(f"range out of scene bounds {s:#x}..{e:#x}")
            ranges.append((s, e))
    ranges.sort()
    for i in range(1, len(ranges)):
        if ranges[i][0] < ranges[i - 1][1]:
            fail("overlapping canary ranges")
    total = sum(e - s for s, e in ranges)

    print(f"copying BIN ({os.path.getsize(BIN_PATH)} bytes)...")
    shutil.copyfile(BIN_PATH, OUT_BIN)

    with open(OUT_BIN, "r+b") as f:
        for s, e in ranges:
            f.seek(TRACK02_OFFSET + SCENE_ISO_BASE + s)
            n = e - s
            f.write((PATTERN * (n // 2 + 1))[:n])

    # 전수 재검증: track02 슬라이스 비교
    print("auditing full track02 diff...")
    plan = {}
    for s, e in ranges:
        for i in range(s, e):
            plan[SCENE_ISO_BASE + i] = PATTERN[(i - s) % 2]
    diff_count = 0
    with open(BIN_PATH, "rb") as fo, open(OUT_BIN, "rb") as fn:
        fo.seek(TRACK02_OFFSET)
        fn.seek(TRACK02_OFFSET)
        remaining = TRACK02_SECTORS * 2048
        pos = 0
        while remaining:
            n = min(1 << 20, remaining)
            a = fo.read(n)
            b = fn.read(n)
            if a != b:
                for j in range(n):
                    if a[j] != b[j]:
                        iso_off = pos + j
                        exp = plan.get(iso_off)
                        if exp is None or b[j] != exp:
                            fail(f"unplanned diff at iso {iso_off:#x}: {a[j]:02X}->{b[j]:02X}")
                        diff_count += 1
            pos += n
            remaining -= n
    planned_changes = sum(1 for off, v in plan.items() if v != _orig_byte(off))
    if diff_count != planned_changes:
        fail(f"diff count {diff_count} != planned effective changes {planned_changes}")

    # BIN의 track02 밖 영역 동일성: 크기 동일 + 앞뒤 슬라이스 해시 비교
    size = os.path.getsize(BIN_PATH)
    if os.path.getsize(OUT_BIN) != size:
        fail("output size mismatch")
    for a, b in ((0, TRACK02_OFFSET),
                 (TRACK02_OFFSET + TRACK02_SECTORS * 2048, size)):
        if _slice_sha(BIN_PATH, a, b - a) != _slice_sha(OUT_BIN, a, b - a):
            fail(f"outside-track02 region modified: {a}..{b}")

    cue = open(CUE_PATH, "r", encoding="utf-8", newline="").read()
    cue_out = cue.replace(
        os.path.basename(BIN_PATH), os.path.basename(OUT_BIN))
    if os.path.basename(OUT_BIN) not in cue_out:
        fail("CUE rewrite failed")
    with open(OUT_CUE, "w", encoding="utf-8", newline="") as f:
        f.write(cue_out)

    manifest = {
        "format": "ZIRIA-Z8-9-CANARY-BUILD",
        "version": 1,
        "purpose": "diagnostic only — MUST NOT be a release input",
        "pattern": "00 E7 repeating (BRK trap + visible garbage)",
        "ranges": [
            {"scene_offset_start": s, "scene_offset_end": e, "bytes": e - s}
            for s, e in ranges
        ],
        "total_fill_bytes": total,
        "effective_changed_bytes": diff_count,
        "source_bin_sha256": BIN_SHA256,
        "output_bin_sha256": sha256_file(OUT_BIN),
        "runtime_gate": [
            "System Card -> title -> first field 정상",
            "첫 대사, NPC 대화, Memo 진입·복귀 정상",
            "첫 전투 공격·필드 복귀 정상",
            "탑 진입, 초상화 대사 정상",
            "화면 깨짐·EXEC BRK·진행 정지 0건",
        ],
        "on_failure": "실패 증상과 위치를 기록하고 해당 구간을 후보에서 제거 후 재배치",
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    print("Z8.9 CANARY BUILD: PASS")
    print(f"  ranges: {len(ranges)}, fill {total} B, effective changes {diff_count} B")
    print(f"  output: {os.path.basename(OUT_BIN)}")
    print(f"  sha256: {manifest['output_bin_sha256']}")


_orig_cache = {}


def _orig_byte(iso_off):
    blk = iso_off >> 12
    if blk not in _orig_cache:
        with open(BIN_PATH, "rb") as f:
            f.seek(TRACK02_OFFSET + (blk << 12))
            _orig_cache[blk] = f.read(1 << 12)
    return _orig_cache[blk][iso_off & 0xFFF]


def _slice_sha(path, offset, length):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(offset)
        remaining = length
        while remaining:
            c = f.read(min(1 << 22, remaining))
            if not c:
                break
            h.update(c)
            remaining -= len(c)
    return h.hexdigest().upper()


if __name__ == "__main__":
    main()
