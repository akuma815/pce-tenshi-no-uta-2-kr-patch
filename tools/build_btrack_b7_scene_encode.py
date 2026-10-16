#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B7 — 씬별 한국어 페이로드 인코딩 (b4 field 인코더의 씬 일반화).

사용: python tools/build_btrack_b7_scene_encode.py <scene_lba> [...]

입력: module_relink/z9_scene_refs/scene_<lba>/dialogue_reference_catalog.csv
      (analyze_ziria_z9_scene_refs.py 산출, status PASS 필수)
      + btrack_b3_translation_map.tsv + btrack_slot_assignment.json
인코딩·재줄바꿈 규칙은 build_btrack_b4_field_encode.py 의 함수를 그대로
임포트해 사용한다 (규칙 이원화 금지).

redirect 대상 = INLINE_OPCODE_* + MEMO_POINTER_TARGET (field 와 동일하게
Memo 는 인코딩만 하고 서빙은 기본 스트림 경로만 — ptr52 는 Z9 후속).
제외 kind (MEMO_TABLE_ROW/FALSE_POSITIVE_TABLE/STRING_TABLE_MEMBER/
SUSPECT_DATA_TABLE) 는 원문 유지.

출력: translation/btrack_b7_scene_<lba>_payload.json
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B3 = ROOT / "translation" / "btrack_b3_translation_map.tsv"
ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
CAT_BASE = ROOT / "module_relink" / "z9_scene_refs"

INCLUDE_KINDS = ("INLINE_OPCODE_02", "INLINE_OPCODE_03", "INLINE_OPCODE_14",
                 "MEMO_POINTER_TARGET")
TEXT_BUDGET = 3 * 8192          # $7C/$7D/$7E
INDEX_ENTRY_BYTES = 7           # b6 인덱스 엔트리
INDEX_FIXED = 2 + 24 * 2        # magic + bucket ptrs


def load_b4_encoder():
    spec = importlib.util.spec_from_file_location(
        "b4enc", ROOT / "tools" / "build_btrack_b4_field_encode.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    lbas = [int(a) for a in sys.argv[1:]]
    if not lbas:
        raise SystemExit("사용: build_btrack_b7_scene_encode.py <scene_lba> ...")
    enc = load_b4_encoder()
    assign = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    slot_sjis = {ch: bytes.fromhex(e["sjis"]) for ch, e in assign.items()}
    b3 = {r["id"]: r for r in csv.DictReader(
        B3.open(encoding="utf-8", newline=""), delimiter="\t")}

    ok = True
    for lba in lbas:
        scene_dir = CAT_BASE / f"scene_{lba}"
        m = json.loads((scene_dir / "manifest.json").read_text(encoding="utf-8"))
        if m["status"] != "PASS":
            raise ValueError(f"scene {lba}: 분석 status {m['status']} — PASS 필요")
        rows = list(csv.DictReader(
            (scene_dir / "dialogue_reference_catalog.csv").open(
                encoding="utf-8-sig", newline="")))

        records = []
        errors = []
        total = 0
        line_over = 0
        excluded = 0
        for e in rows:
            if e["reference_kind"] not in INCLUDE_KINDS:
                excluded += 1
                continue
            rid = e["id"]
            b = b3.get(rid)
            if b is None:
                errors.append((rid, "B3 맵에 없음"))
                continue
            ko = enc.repaginate(b["ko"])
            for page in ko.split(enc.BSP):
                for ln in page.split(enc.BSN):
                    if enc.cells(ln) > enc.LINE_MAX:
                        line_over += 1
            try:
                data = enc.encode_stream(ko, slot_sjis)
            except enc.EncodeError as ex:
                errors.append((rid, str(ex)))
                continue
            total += len(data)
            records.append({
                "id": rid, "master_id": rid, "b3_status": b["status"],
                "source_key_u24le": e["source_key_u24le"],
                "original_raw_length": int(e["raw_length"]),
                "reference_kind": e["reference_kind"],
                "ko_repaginated": ko,
                "encoded_hex": data.hex().upper(),
                "encoded_length": len(data),
            })

        if errors:
            ok = False
        index_reserve = INDEX_FIXED + len(records) * INDEX_ENTRY_BYTES + 24
        fit = total <= TEXT_BUDGET and index_reserve <= 0x780
        if not fit:
            ok = False
        manifest = {
            "format": "BTRACK-B7-SCENE-PAYLOAD",
            "scene_lba": lba,
            "records": len(records),
            "excluded_non_redirect": excluded,
            "errors": errors,
            "line_over_24": line_over,
            "text_bytes_total": total,
            "text_budget": TEXT_BUDGET,
            "index_reserve": index_reserve,
            "fit": fit,
            "catalog_sha256": m["catalog_sha256"],
        }
        out = ROOT / "translation" / f"btrack_b7_scene_{lba}_payload.json"
        out.write_text(json.dumps({"manifest": manifest, "records": records},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: manifest[k] for k in
                          ("scene_lba", "records", "excluded_non_redirect",
                           "text_bytes_total", "index_reserve", "fit",
                           "line_over_24")} | {"errors": len(errors)},
                         ensure_ascii=False))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
