#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B9 — master 추출 누락 대사 보충 페이로드 생성.

배경 (2026-08-28 사용자 게이트에서 발견, HANDOFF §1 triage 경로):
2882 의 지진 이벤트 대사가 일문 잔존 → 전수 조사 결과 **master 대사
모집단에 빠진 인라인(02/03/14) 레코드**가 54씬에 13종/18인스턴스 존재
(forensic 광역 스캔 대조, `translation/b9_master_gap_census.tsv` /
`b9_master_gap_real.tsv`). 나머지 후보는 공유 블록 반복 데이터·천사어
암호문(원작 의도 유지)·쓰레기 문자열로 판정 제외.

입력: translation/b9_gap_supplement_source.tsv (id/scene/consumer/
review_status/jp/ko — ko 는 b3 맵과 동일한 리터럴 \\n·\\p 표기).
초벌(draft) 번역은 인간 검토 대상 — 릴리스 전 필수 (개발 빌드는 선언 진행).

인코딩·재줄바꿈은 b4 인코더 함수를 그대로 사용 (규칙 이원화 금지).
source key = iso_offset - lba*2048 (scene-relative — b4 페이로드 실측 검증),
original_raw_length = 디스크 레코드 길이(NUL 포함, ISO 실측).

출력: translation/btrack_b9_gap_supplement_payload.json
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
SRC = ROOT / "translation" / "b9_gap_supplement_source.tsv"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
OUT = ROOT / "translation" / "btrack_b9_gap_supplement_payload.json"

SCENE_SECTORS = {290: 96, 386: 96, 482: 96, 578: 78, 674: 96, 770: 96,
                 866: 96, 962: 96, 1058: 83, 1154: 96, 1250: 96, 1346: 96,
                 1442: 96, 1538: 73, 1634: 96, 1730: 92, 1826: 96, 1922: 96,
                 2018: 82, 2114: 75, 2210: 76, 2306: 96, 2402: 96, 2498: 71,
                 2594: 71, 2690: 96, 2786: 69, 2882: 96, 2978: 94, 3074: 96,
                 3170: 96, 3266: 96, 3362: 96, 3458: 96, 3554: 84, 3650: 84,
                 3746: 96, 3842: 96, 3938: 96, 4034: 75, 4130: 96, 4226: 96,
                 4322: 96, 4418: 80, 4514: 82, 4610: 81, 4706: 81, 4802: 90,
                 4898: 76, 4994: 76, 5090: 84, 5186: 96, 5282: 96, 5378: 96}


def load_b4_encoder():
    spec = importlib.util.spec_from_file_location(
        "b4enc", ROOT / "tools" / "build_btrack_b4_field_encode.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def existing_scene_keys(lba: int) -> set[int]:
    name = ("btrack_b4_field_payload.json" if lba == 482
            else f"btrack_b7_scene_{lba}_payload.json")
    pl = json.loads((ROOT / "translation" / name
                     ).read_text(encoding="utf-8"))["records"]
    return {int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little")
            for r in pl}


def main() -> None:
    iso = ISO.read_bytes()
    enc = load_b4_encoder()
    assign = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    slot_sjis = {ch: bytes.fromhex(e["sjis"]) for ch, e in assign.items()}

    scenes: dict[str, list] = {}
    errors = []
    line_over = 0
    seen_keys: dict[int, set[int]] = {}
    with SRC.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        rid = r["id"]
        off = int(rid.split(":")[1], 16)
        lba = int(r["scene"])
        start, end = lba * 2048, (lba + SCENE_SECTORS[lba]) * 2048
        if not (start <= off < end):
            raise ValueError(f"{rid}: scene {lba} extent 밖")
        nul = iso.index(0, off)
        raw = iso[off:nul + 1]
        if len(raw) < 2 or len(raw) > 4096:
            raise ValueError(f"{rid}: raw 길이 이상 {len(raw)}")
        op = iso[off - 1]
        if r["consumer"] == "opcode02":
            if op not in (0x02, 0x03, 0x14):
                raise ValueError(f"{rid}: 선행 opcode {op:02X} ∉ 02/03/14")
        elif r["consumer"] != "continuation":
            raise ValueError(f"{rid}: consumer {r['consumer']} 미지원")
        key = off - start
        assert key < (1 << 24)
        ks = seen_keys.setdefault(lba, existing_scene_keys(lba))
        if key in ks:
            raise ValueError(f"{rid}: 씬 {lba} 기존 키와 충돌 {key:06X}")
        ks.add(key)

        ko = enc.repaginate(r["ko"])
        for page in ko.split(enc.BSP):
            for ln in page.split(enc.BSN):
                if enc.cells(ln) > enc.LINE_MAX:
                    line_over += 1
        try:
            data = enc.encode_stream(ko, slot_sjis)
        except enc.EncodeError as ex:
            errors.append((rid, str(ex)))
            continue
        scenes.setdefault(str(lba), []).append({
            "id": rid, "master_id": rid,
            "b3_status": f"GAP_SUPPLEMENT_{r['review_status'].upper()}",
            "source_key_u24le": key.to_bytes(3, "little").hex().upper(),
            "original_raw_length": len(raw),
            "reference_kind": "GAP_SUPPLEMENT_" + r["consumer"].upper(),
            "ko_repaginated": ko,
            "encoded_hex": data.hex().upper(),
            "encoded_length": len(data),
        })

    if errors:
        for rid, e in errors:
            print(f"ERROR {rid}: {e}")
        sys.exit(1)
    manifest = {
        "format": "BTRACK-B9-GAP-SUPPLEMENT",
        "records": sum(len(v) for v in scenes.values()),
        "scenes": {k: len(v) for k, v in scenes.items()},
        "line_over_24": line_over,
        "review": "draft 행은 릴리스 전 인간 검토 필수 "
                  "(2026-08-28 초벌 — 용어는 기존 번역 준수: "
                  "지아/기밀/여행 일지가/풍도사촌/바엘)",
    }
    OUT.write_text(json.dumps({"manifest": manifest, "scenes": scenes},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
