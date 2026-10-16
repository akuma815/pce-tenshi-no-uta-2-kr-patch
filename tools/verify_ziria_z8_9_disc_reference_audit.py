#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9a 독립 검증기.

build_ziria_z8_9_disc_reference_audit.py의 manifest를 다음 기준으로 검증한다.

1. 원본 Track02 슬라이스 해시가 manifest 기준과 일치한다.
2. 승인 구간이 어떤 정적/런타임 참조 extent와도 겹치지 않는다.
3. 승인 구간의 원본 내용이 바이트 단위로 전부 승인 fill 값이다.
4. 승인 구간이 규칙(run 최소 길이, 예약 하한, fill 값)을 만족한다.
5. 두 55-entry 테이블을 원본에서 재파싱한 값이 manifest와 동일하다.
6. 빌드를 재실행해도 manifest가 바이트 단위로 동일하다(결정성).

실패 시 종료 코드 1.
"""

import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
MANIFEST = os.path.join(ROOT, "translation", "ziria_z8_9_disc_reference_audit_manifest.json")
BUILDER = os.path.join(ROOT, "tools", "build_ziria_z8_9_disc_reference_audit.py")


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    with open(MANIFEST, "r", encoding="utf-8") as f:
        m = json.load(f)

    src = m["source"]
    off = src["track02_bin_offset"]
    sectors = src["track02_sectors"]

    h = hashlib.sha256()
    with open(BIN_PATH, "rb") as f:
        f.seek(off)
        remaining = sectors * 2048
        while remaining:
            chunk = f.read(min(1 << 22, remaining))
            h.update(chunk)
            remaining -= len(chunk)
    if h.hexdigest().upper() != src["track02_sha256"]:
        fail("track02 slice hash mismatch")

    with open(BIN_PATH, "rb") as f:
        f.seek(off)
        data = f.read(sectors * 2048)

    # 테이블 재파싱 대조
    for key, toff in (("primary_table", 0x424A5), ("scene_table", 0x83531)):
        if m["static_references"][f"{key}_offset"] != hex(toff):
            fail(f"{key} offset mismatch")
        raw = data[toff:toff + 55 * 4]
        for i, entry in enumerate(m["static_references"][key]):
            hi, mid, lo, cnt = raw[i * 4:i * 4 + 4]
            lba = (hi << 16) | (mid << 8) | lo
            if entry["lba"] != lba or entry["sector_count"] != cnt:
                fail(f"{key} entry {i} mismatch")

    # 참조 extent 수집
    ref = []
    for km in m["static_references"]["known_modules"]:
        ref.append((km["lba"], km["lba"] + km["sector_count"]))
    for key in ("primary_table", "scene_table"):
        for e in m["static_references"][key]:
            ref.append((e["lba"], e["lba"] + e["sector_count"]))
    for e in m["runtime_observed_extents"]:
        ref.append((e["lba"], e["lba"] + e["sector_count"]))

    rules = m["rules"]
    approved = m["approved_regions"]
    if not approved:
        print("VERIFY: no approved region (nothing to check beyond hashes)")
    for a in approved:
        s, e = a["lba_start"], a["lba_end"]
        if e <= s or e > sectors:
            fail(f"approved region bounds invalid {a}")
        if e - s < rules["min_approve_run_sectors"]:
            fail(f"approved region shorter than min run {a}")
        if s < rules["first_scene_slot_reserved_below"]:
            fail(f"approved region inside reserved system area {a}")
        if a["fill_value"] != rules["approve_fill_value"]:
            fail(f"approved region fill value mismatch {a}")
        for rs, re_ in ref:
            if max(s, rs) < min(e, re_):
                fail(f"approved region overlaps reference {rs}..{re_}")
        blob = data[s * 2048:e * 2048]
        if blob.count(rules["approve_fill_value"]) != len(blob):
            fail(f"approved region not pure fill {a}")

    total = sum(a["sectors"] for a in approved)
    if total != m["approved_total_sectors"]:
        fail("approved_total_sectors mismatch")
    if total * 2048 != m["approved_total_bytes"]:
        fail("approved_total_bytes mismatch")

    # 결정성: 빌드 재실행 후 manifest 바이트 비교
    before = open(MANIFEST, "rb").read()
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", BUILDER],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        fail(f"builder rerun failed: {proc.stderr.strip()}")
    after = open(MANIFEST, "rb").read()
    if before != after:
        fail("manifest is not deterministic across reruns")

    print(
        "Z8.9a DISC AUDIT VERIFY: PASS "
        f"(approved {len(approved)} region(s), {total} sectors, {total * 2048} bytes)"
    )


if __name__ == "__main__":
    main()
