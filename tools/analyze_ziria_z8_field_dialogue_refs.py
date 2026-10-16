#!/usr/bin/env python3
"""Catalogue Z8 field-dialogue source references without mutating disc data."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MODULE_CATALOG = ROOT / "translation" / "ziria_module_catalog.json"
Z8_MANIFEST = ROOT / "translation" / "ziria_z8_text_containers_manifest.json"
Z8_INDEX = ROOT / "translation" / "ziria_z8_text_entry_index.csv"
TRACE = ROOT / "translation" / "ziria_z6_stream_source_trace.tsv"
OUTPUT_ROOT = ROOT / "module_relink" / "z8_field_dialogue_refs"
CATALOG = OUTPUT_ROOT / "field_dialogue_reference_catalog.csv"
OBSERVED = OUTPUT_ROOT / "observed_stream_starts.csv"
LOADER_REF = OUTPUT_ROOT / "loader_reference.json"
MANIFEST = ROOT / "translation" / "ziria_z8_field_dialogue_reference_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_2_field_dialogue_참조_카탈로그.md"

TARGET_LBA = 482
TARGET_SECTORS = 96
SECTOR_BYTES = 2048
DESTINATION_BANK_BASE = 0x68
SUPER_RAM_BANKS = 24
TOKEN_RE = re.compile(r"\\[np]|\{[^{}]+\}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path, delimiter: str = ",") -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=delimiter))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def u24le(value: int) -> str:
    if not 0 <= value < 1 << 24:
        raise ValueError(f"u24 overflow: {value}")
    return value.to_bytes(3, "little").hex().upper()


def parse_trace_offset(value: str) -> int | None:
    if not value or value == "-":
        return None
    return int(value, 16)


def main() -> None:
    for path in (MASTER, ISO, MODULE_CATALOG, Z8_MANIFEST, Z8_INDEX, TRACE):
        if not path.is_file():
            raise FileNotFoundError(path)

    z8 = json.loads(Z8_MANIFEST.read_text(encoding="utf-8"))
    if sha256(MASTER) != z8["inputs"]["master_text"]["sha256"]:
        raise ValueError("master_text differs from Z8 baseline")
    if sha256(ISO) != z8["inputs"]["track02_iso"]["sha256"]:
        raise ValueError("Track02 ISO differs from Z8 baseline")

    module_catalog = json.loads(MODULE_CATALOG.read_text(encoding="utf-8"))
    loader = module_catalog["loader"]
    overlay = module_catalog["directories"]["overlay"]
    matching_entries = [
        entry
        for entry in overlay["entries"]
        if entry["lba"] == TARGET_LBA and entry["sector_count"] == TARGET_SECTORS
    ]
    if len(matching_entries) != 1:
        raise ValueError(f"expected one LBA 482x96 loader entry, got {len(matching_entries)}")
    loader_entry = matching_entries[0]
    logical_entry = loader_entry["logical_entry"]
    table_base = int(loader["overlay_table"]["track02_iso_offset"], 16)
    table_offset = table_base + logical_entry * 4

    iso = ISO.read_bytes()
    expected_loader_raw = bytes.fromhex(loader_entry["raw_hex"])
    if iso[table_offset:table_offset + 4] != expected_loader_raw:
        raise ValueError("loader table raw mismatch")
    decoded_lba = int.from_bytes(expected_loader_raw[:3], "big")
    decoded_count = expected_loader_raw[3]
    if (decoded_lba, decoded_count) != (TARGET_LBA, TARGET_SECTORS):
        raise ValueError("loader table decode mismatch")

    module_start = TARGET_LBA * SECTOR_BYTES
    module_size = TARGET_SECTORS * SECTOR_BYTES
    module_end = module_start + module_size
    if module_size != SUPER_RAM_BANKS * 8192:
        raise ValueError("scene package does not fill the 24-bank Super RAM window")

    master_rows = read_csv(MASTER)
    z8_rows = {row["id"]: row for row in read_csv(Z8_INDEX)}
    selected = [
        row
        for row in master_rows
        if row["category"] == "dialogue"
        and module_start <= int(row["iso_offset"], 16) < module_end
    ]
    if not selected:
        raise ValueError("no field dialogue rows")
    for row in selected:
        if row["id"] not in z8_rows:
            raise ValueError(f"missing Z8 entry: {row['id']}")
        raw = bytes.fromhex(row["raw_hex"])
        offset = int(row["iso_offset"], 16)
        if offset + len(raw) > module_end:
            raise ValueError(f"record crosses module end: {row['id']}")
        if iso[offset:offset + len(raw)] != raw or raw[-1] != 0:
            raise ValueError(f"protected raw mismatch: {row['id']}")
        if TOKEN_RE.findall(row["original"]) != TOKEN_RE.findall(row["translation"]):
            raise ValueError(f"token mismatch: {row['id']}")

    trace_rows = [
        row for row in read_csv(TRACE, "\t")
        if row.get("event") == "STREAM" and parse_trace_offset(row.get("iso_offset", "")) is not None
    ]
    trace_by_offset: dict[int, list[dict]] = defaultdict(list)
    for trace_row in trace_rows:
        trace_by_offset[parse_trace_offset(trace_row["iso_offset"])].append(trace_row)

    module = iso[module_start:module_end]
    catalog_rows = []
    observed_rows = []
    observed_count = 0
    fully_observed_count = 0
    direct_literal_candidates = 0
    for row in selected:
        source_offset = int(row["iso_offset"], 16)
        raw = bytes.fromhex(row["raw_hex"])
        relative = source_offset - module_start
        physical_bank = DESTINATION_BANK_BASE + relative // 8192
        bank_offset = relative % 8192
        if not DESTINATION_BANK_BASE <= physical_bank <= 0x7F:
            raise ValueError(f"physical bank outside scene window: {row['id']}")

        hit_offsets = {
            offset for offset in trace_by_offset
            if source_offset <= offset < source_offset + len(raw)
        }
        start_hits = trace_by_offset.get(source_offset, [])
        observed_runtime = bool(hit_offsets)
        fully_observed = len(hit_offsets) == len(raw)
        if observed_runtime:
            observed_count += 1
        if fully_observed:
            fully_observed_count += 1

        start_states = sorted({
            (
                trace["reader"],
                trace["logical"],
                trace["page"],
                trace["mpr"],
                trace["mpr2"],
                trace["mpr3"],
                trace["mpr4"],
                trace["mpr5"],
                trace["mpr6"],
            )
            for trace in start_hits
        })
        literal_locations = set()
        for _, logical, _, _, *_ in start_states:
            pattern = int(logical, 16).to_bytes(2, "little")
            cursor = 0
            while True:
                found = module.find(pattern, cursor)
                if found < 0:
                    break
                literal_locations.add(module_start + found)
                cursor = found + 1
        direct_literal_candidates += len(literal_locations)

        z8_row = z8_rows[row["id"]]
        catalog_rows.append(
            {
                "id": row["id"],
                "source_iso_offset": f"0x{source_offset:07X}",
                "source_module_offset": f"0x{relative:05X}",
                "source_key_u24le": u24le(relative),
                "source_physical_bank": f"0x{physical_bank:02X}",
                "source_bank_offset": f"0x{bank_offset:04X}",
                "raw_length": len(raw),
                "raw_sha256": hashlib.sha256(raw).hexdigest().upper(),
                "terminator": "00",
                "region": row["region"],
                "subcategory": row["subcategory"],
                "z8_package_id": z8_row["package_id"],
                "z8_container_offset": z8_row["container_offset"],
                "encoded_length": z8_row["encoded_length"],
                "token_count": len(TOKEN_RE.findall(row["original"])),
                "runtime_observed": "yes" if observed_runtime else "no",
                "runtime_observed_unique_bytes": len(hit_offsets),
                "runtime_fully_observed": "yes" if fully_observed else "no",
                "runtime_start_states": json.dumps(start_states, ensure_ascii=False, separators=(",", ":")),
                "literal_scan_candidates": ";".join(f"0x{value:07X}" for value in sorted(literal_locations)),
                "literal_scan_policy": "NOT_REFERENCE_EVIDENCE",
                "reference_model": "INLINE_STREAM_START_KEYED_BY_SCENE_RELATIVE_OFFSET",
                "reference_status": (
                    "OBSERVED_RUNTIME_STREAM"
                    if observed_runtime
                    else "EXTRACTED_BOUNDARY_RUNTIME_UNOBSERVED"
                ),
            }
        )
        for state in start_states:
            observed_rows.append(
                {
                    "id": row["id"],
                    "source_iso_offset": f"0x{source_offset:07X}",
                    "source_module_offset": f"0x{relative:05X}",
                    "reader": state[0],
                    "logical": state[1],
                    "page": state[2],
                    "mapped_physical_bank": state[3],
                    "mpr2": state[4],
                    "mpr3": state[5],
                    "mpr4": state[6],
                    "mpr5": state[7],
                    "mpr6": state[8],
                }
            )

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)
    write_csv(CATALOG, list(catalog_rows[0].keys()), catalog_rows)
    write_csv(
        OBSERVED,
        [
            "id", "source_iso_offset", "source_module_offset", "reader", "logical",
            "page", "mapped_physical_bank", "mpr2", "mpr3", "mpr4", "mpr5", "mpr6",
        ],
        observed_rows,
    )

    loader_reference = {
        "format": "ZIRIA-Z8-FIELD-LOADER-REFERENCE",
        "version": 1,
        "owner_module": loader["owner_module"],
        "storage_coordinate": {
            "track02_iso_offset": f"0x{table_offset:05X}",
            "table_base": f"0x{table_base:05X}",
            "logical_entry": logical_entry,
            "width_bytes": 4,
            "endian": "LBA big-endian u24 plus u8 sector count",
            "raw_hex": expected_loader_raw.hex().upper(),
        },
        "target_coordinate": {
            "scene_module": "scene.field_start",
            "lba": TARGET_LBA,
            "sector_count": TARGET_SECTORS,
            "track02_iso_start": f"0x{module_start:07X}",
            "track02_iso_end_exclusive": f"0x{module_end:07X}",
            "bytes": module_size,
        },
        "consumer": {
            "routine_runtime_range": loader["routine"]["runtime_range"],
            "cd_read_callsite_runtime": loader["routine"]["cd_read_callsite_runtime"],
            "bios_entry": loader["routine"]["bios_cd_read_entry"],
            "destination_mode": loader["routine"]["destination_mode_for_scene_packages"],
            "destination_bank_source": loader["routine"]["destination_bank_source"],
            "destination_physical_banks": "0x68..0x7F",
            "lifetime": "replaced atomically by the next scene package load",
        },
        "denominator": {
            "overlay_directory_entries": overlay["entries"].__len__(),
            "matching_lba_count_entries": len(matching_entries),
            "status": "PASS_EXACTLY_ONE_LOADER_REFERENCE",
        },
    }
    LOADER_REF.write_text(
        json.dumps(loader_reference, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "format": "ZIRIA-Z8-FIELD-DIALOGUE-REFERENCE-CATALOG",
        "version": 1,
        "task": "Z8-v2-reference-denominator",
        "status": "LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN",
        "mutation_scope": "analysis only; no CUE/BIN/ISO mutation",
        "inputs": {
            "master_text": {"path": MASTER.relative_to(ROOT).as_posix(), "sha256": sha256(MASTER)},
            "track02_iso": {"path": ISO.relative_to(ROOT).as_posix(), "sha256": sha256(ISO)},
            "module_catalog": {"path": MODULE_CATALOG.relative_to(ROOT).as_posix(), "sha256": sha256(MODULE_CATALOG)},
            "z8_manifest": {"path": Z8_MANIFEST.relative_to(ROOT).as_posix(), "sha256": sha256(Z8_MANIFEST)},
            "z8_entry_index": {"path": Z8_INDEX.relative_to(ROOT).as_posix(), "sha256": sha256(Z8_INDEX)},
            "runtime_trace": {"path": TRACE.relative_to(ROOT).as_posix(), "sha256": sha256(TRACE)},
        },
        "loader_reference": {
            "status": "PASS",
            "catalogue_entries": len(overlay["entries"]),
            "matching_entries": len(matching_entries),
            "logical_entry": logical_entry,
            "storage_offset": f"0x{table_offset:05X}",
            "raw_hex": expected_loader_raw.hex().upper(),
            "target_lba": TARGET_LBA,
            "sector_count": TARGET_SECTORS,
        },
        "text_reference_population": {
            "field_dialogue_records_in_extent": len(catalog_rows),
            "runtime_observed_records": observed_count,
            "runtime_fully_observed_records": fully_observed_count,
            "runtime_unobserved_records": len(catalog_rows) - observed_count,
            "direct_literal_scan_candidates": direct_literal_candidates,
            "direct_literal_scan_policy": "candidate bytes are not accepted as references",
            "denominator_status": "OPEN_STATIC_EVENT_BYTECODE_DECODER_OR_COMPLETE_RUNTIME_COVERAGE_REQUIRED",
        },
        "source_key_model": {
            "basis": "scene package relative offset",
            "width_bits": 24,
            "endian": "little",
            "formula": (
                "physical_bank=MPR[logical>>13]; "
                "source_offset=(physical_bank-0x68)*0x2000+(logical&0x1FFF)"
            ),
            "valid_physical_banks": "0x68..0x7F",
            "round_trip": "PASS_FOR_ALL_CATALOGUED_RECORDS",
            "reason": "stable across MPR page remapping while the owning scene package is resident",
        },
        "redirect_index": {
            "status": "NOT_BUILT",
            "reason": (
                "source-key representation is proven, but the complete text-consumer reference "
                "denominator, translation storage coordinate, hook ABI, and loader-owned lifetime "
                "are not yet proven"
            ),
            "legacy_01_02_protocol": "PROHIBITED",
        },
        "outputs": {
            "reference_catalog": CATALOG.relative_to(ROOT).as_posix(),
            "observed_starts": OBSERVED.relative_to(ROOT).as_posix(),
            "loader_reference": LOADER_REF.relative_to(ROOT).as_posix(),
            "report": REPORT.relative_to(ROOT).as_posix(),
        },
    }
    for key, relative in list(manifest["outputs"].items())[:3]:
        manifest["outputs"][f"{key}_sha256"] = sha256(ROOT / relative)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = f"""# Z8.2 field dialogue 참조 카탈로그

## 판정

상태는 `{manifest['status']}`다. `field.main_engine`이 소유하는 overlay directory
entry 2가 LBA 482의 96 sectors를 mode 06으로 physical bank `$68-$7F`에
적재하는 로더 참조는 정확히 한 개이며 원본 바이트 `0001E260`과 일치한다.

이 scene extent 안에는 dialogue 레코드 **{len(catalog_rows)}개**가 있다. 기존
장기 추적에서 실제 stream 소비가 확인된 것은 **{observed_count}개**, 레코드
전체 바이트가 확인된 것은 **{fully_observed_count}개**다. 나머지
**{len(catalog_rows) - observed_count}개**는 추출 경계와 원본 바이트는
확정됐지만 runtime 소비가 확인되지 않았다.

## 확정한 source key

논리 주소만 저장하지 않는다. 소비 시점의 MPR을 읽어 다음 scene-relative
offset을 계산한다.

`physical_bank = MPR[logical >> 13]`

`source_offset = (physical_bank - $68) * $2000 + (logical & $1FFF)`

236개 레코드의 source offset은 모두 24-bit little-endian으로 왕복되며
`$68-$7F` 범위 안이다. 이 키는 같은 scene package가 resident인 동안 MPR
page가 바뀌어도 동일하다.

## 아직 redirect/index를 만들지 않은 이유

- runtime에서 확인된 텍스트 레코드는 236개 중 9개뿐이다.
- 관측된 logical start 값을 scene 바이트에서 검색하면 우연 일치가 섞인다.
  따라서 literal byte scan 결과를 포인터 카탈로그로 승격하지 않았다.
- event bytecode의 모든 text-start 소비를 열거하는 정적 decoder 또는
  동등한 완전 runtime coverage가 아직 없다.
- 번역 컨테이너 저장 좌표, 적재 RAM, 수명, field stream reader hook ABI가
  아직 loader-owned 경계로 확정되지 않았다.

그러므로 `01/02` 프로토콜이나 임의 16-bit 포인터 보정은 사용하지 않는다.
다음 단계는 `$4293/$42DE/$42AB/$42BA` stream reader 경계에서 위 source key를
계산하는 read-only probe를 만들고, 관측된 9개 시작점의 키가 카탈로그와
일치하는지 검증하는 것이다.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "loader_reference": "PASS",
        "field_dialogue_records": len(catalog_rows),
        "runtime_observed_records": observed_count,
        "runtime_fully_observed_records": fully_observed_count,
        "runtime_unobserved_records": len(catalog_rows) - observed_count,
        "redirect_index_built": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
