#!/usr/bin/env python3
"""Classify every Z8 field-dialogue catalogue row by its static owner.

This is deliberately read-only.  It does not attempt to translate or relocate
anything.  The goal is to distinguish inline event payloads from the Memo
pointer table and to fail closed on extraction-boundary defects.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
INPUT_CATALOG = (
    ROOT / "module_relink" / "z8_field_dialogue_refs"
    / "field_dialogue_reference_catalog.csv"
)
RUNTIME_MANIFEST = ROOT / "translation" / "ziria_z8_field_source_key_runtime_manifest.json"
OUTPUT_DIR = ROOT / "module_relink" / "z8_field_event_refs"
OUTPUT_CATALOG = OUTPUT_DIR / "field_event_reference_catalog.csv"
MANIFEST = ROOT / "translation" / "ziria_z8_field_event_bytecode_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_5_field_event_bytecode_result.md"

MODULE_START = 482 * 2048
MODULE_END = MODULE_START + 96 * 2048

# These are not guesses.  Each correction is independently asserted against
# an opcode/pointer-table structure below.
PARTIAL_INLINE_STARTS = {
    "iso:010CAE1": 0x010CABD,
    "iso:010D080": 0x010D036,
}
MEMO_POINTERS = [
    (0x011F010, 0xC01E, 0x011F01E),
    (0x011F012, 0xC029, 0x011F029),
    (0x011F014, 0xC031, 0x011F031),
    (0x011F016, 0xC03B, 0x011F03B),
    (0x011F018, 0xC043, 0x011F043),
    (0x011F01A, 0xC04F, 0x011F04F),
    (0x011F01C, 0xC059, 0x011F059),
]
MEMO_CATALOG_IDS = [
    "iso:011F011",
    "iso:011F029",
    "iso:011F031",
    "iso:011F03B",
    "iso:011F043",
    "iso:011F04F",
    "iso:011F059",
]
FALSE_POSITIVE_ID = "iso:010F080"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    for path in (ISO, MASTER, INPUT_CATALOG, RUNTIME_MANIFEST):
        if not path.is_file():
            raise FileNotFoundError(path)

    image = ISO.read_bytes()
    catalogue = read_csv(INPUT_CATALOG)
    master = {row["id"]: row for row in read_csv(MASTER)}
    if len(catalogue) != 236:
        raise ValueError(f"expected 236 input rows, got {len(catalogue)}")

    # Prove the Memo table itself: seven consecutive little-endian logical
    # pointers in page $C000, each resolving to the corresponding NUL string.
    memo_by_id: dict[str, tuple[int, int, int]] = {}
    for row_id, (storage, logical, target) in zip(MEMO_CATALOG_IDS, MEMO_POINTERS):
        raw_pointer = image[storage:storage + 2]
        if int.from_bytes(raw_pointer, "little") != logical:
            raise ValueError(f"Memo pointer mismatch at 0x{storage:07X}")
        if target != MODULE_START + 0x2E000 + (logical - 0xC000):
            raise ValueError(f"Memo pointer does not resolve: 0x{logical:04X}")
        if 0 not in image[target:target + 256]:
            raise ValueError(f"Memo target is not NUL terminated: 0x{target:07X}")
        memo_by_id[row_id] = (storage, logical, target)

    output: list[dict[str, object]] = []
    kinds: Counter[str] = Counter()
    boundaries: Counter[str] = Counter()

    for position, entry in enumerate(catalogue):
        row_id = entry["id"]
        source = int(entry["source_iso_offset"], 16)
        raw = bytes.fromhex(master[row_id]["raw_hex"])
        if image[source:source + len(raw)] != raw:
            raise ValueError(f"master raw mismatch: {row_id}")

        kind = ""
        structural_start: int | None = source
        reference_storage: int | None = None
        reference_raw = ""
        boundary = "EXACT"
        eligible = "yes"
        note = ""

        if row_id == FALSE_POSITIVE_ID:
            # This six-byte run is embedded in a sequential kana lookup table,
            # surrounded by zero padding, and has no event opcode or pointer.
            prefix = bytes(range(0x3F, 0x4E)) + b"\0" + bytes(range(0x4E, 0x53))
            if image[source - 32:source - 11] != prefix:
                raise ValueError("false-positive lookup-table prefix changed")
            if image[source - 11:source] != b"\0" * 11:
                raise ValueError("false-positive lookup-table padding changed")
            if image[source:source + 16] != b"\x53\x54\x55\x56\x57" + b"\0" * 11:
                raise ValueError("false-positive lookup-table suffix changed")
            kind = "FALSE_POSITIVE_KANA_TABLE"
            structural_start = None
            boundary = "EXCLUDE"
            eligible = "no"
            note = "sequential kana lookup table; not an event text consumer"
        elif row_id in memo_by_id:
            storage, logical, target = memo_by_id[row_id]
            kind = "MEMO_POINTER_TABLE"
            structural_start = target
            reference_storage = storage
            reference_raw = image[storage:storage + 2].hex().upper()
            if source != target:
                boundary = "MASTER_PREFIX_OVERREAD"
                eligible = "no"
                note = (
                    f"master starts at 0x{source:07X}; pointer resolves to "
                    f"0x{target:07X}"
                )
        elif row_id in PARTIAL_INLINE_STARTS:
            structural_start = PARTIAL_INLINE_STARTS[row_id]
            opcode_at = structural_start - 1
            if image[opcode_at] != 0x02 or not opcode_at < source:
                raise ValueError(f"partial inline signature mismatch: {row_id}")
            if 0 in image[structural_start:source]:
                raise ValueError(f"partial inline prefix crosses NUL: {row_id}")
            if image[source + len(raw) - 1] != 0:
                raise ValueError(f"partial inline lacks terminator: {row_id}")
            kind = "INLINE_OPCODE_02"
            reference_storage = opcode_at
            reference_raw = "02"
            boundary = "MASTER_PREFIX_UNDERREAD"
            eligible = "no"
            note = (
                f"actual payload starts at 0x{structural_start:07X}; "
                f"master omits {source - structural_start} bytes"
            )
        else:
            opcode = image[source - 1]
            if opcode not in (0x02, 0x03, 0x14):
                raise ValueError(
                    f"unclassified row {row_id}: preceding byte 0x{opcode:02X}"
                )
            kind = f"INLINE_OPCODE_{opcode:02X}"
            reference_storage = source - 1
            reference_raw = f"{opcode:02X}"
            if raw[-1] != 0:
                raise ValueError(f"inline payload lacks terminator: {row_id}")

        if structural_start is not None and not MODULE_START <= structural_start < MODULE_END:
            raise ValueError(f"structural start outside scene: {row_id}")

        kinds[kind] += 1
        boundaries[boundary] += 1
        output.append(
            {
                "catalogue_position": position,
                "id": row_id,
                "catalog_source_iso_offset": f"0x{source:07X}",
                "structural_source_iso_offset": (
                    "" if structural_start is None else f"0x{structural_start:07X}"
                ),
                "structural_module_offset": (
                    "" if structural_start is None
                    else f"0x{structural_start - MODULE_START:05X}"
                ),
                "reference_kind": kind,
                "reference_storage_iso_offset": (
                    "" if reference_storage is None
                    else f"0x{reference_storage:07X}"
                ),
                "reference_raw_hex": reference_raw,
                "boundary_status": boundary,
                "redirect_eligible": eligible,
                "runtime_observed": entry["runtime_observed"],
                "note": note,
            }
        )

    expected_kinds = {
        "INLINE_OPCODE_02": 217,
        "INLINE_OPCODE_03": 10,
        "INLINE_OPCODE_14": 1,
        "MEMO_POINTER_TABLE": 7,
        "FALSE_POSITIVE_KANA_TABLE": 1,
    }
    expected_boundaries = {
        "EXACT": 232,
        "MASTER_PREFIX_UNDERREAD": 2,
        "MASTER_PREFIX_OVERREAD": 1,
        "EXCLUDE": 1,
    }
    if dict(kinds) != expected_kinds:
        raise ValueError(f"unexpected reference-kind population: {dict(kinds)}")
    if dict(boundaries) != expected_boundaries:
        raise ValueError(f"unexpected boundary population: {dict(boundaries)}")

    write_csv(OUTPUT_CATALOG, output)
    manifest = {
        "format": "ZIRIA-Z8-FIELD-EVENT-BYTECODE",
        "version": 1,
        "task": "Z8.5-static-event-reference-denominator",
        "status": "STATIC_DENOMINATOR_PASS_BOUNDARY_REPAIR_REQUIRED",
        "mutation_scope": "analysis outputs only; no CUE/BIN/ISO mutation",
        "inputs": {
            "track02_iso": {"path": ISO.relative_to(ROOT).as_posix(), "sha256": sha256(ISO)},
            "master_text": {"path": MASTER.relative_to(ROOT).as_posix(), "sha256": sha256(MASTER)},
            "input_catalog": {
                "path": INPUT_CATALOG.relative_to(ROOT).as_posix(),
                "sha256": sha256(INPUT_CATALOG),
            },
            "runtime_manifest": {
                "path": RUNTIME_MANIFEST.relative_to(ROOT).as_posix(),
                "sha256": sha256(RUNTIME_MANIFEST),
            },
        },
        "population": {
            "input_rows": len(catalogue),
            "structural_text_consumers": 235,
            "reference_kinds": dict(kinds),
            "boundary_status": dict(boundaries),
            "redirect_eligible_exact_rows": 232,
            "boundary_repairs_required": 3,
            "excluded_false_positives": 1,
        },
        "model": {
            "inline": (
                "opcode 02/03/14 immediately owns a NUL-terminated text payload; "
                "there is no independent pointer to relocate"
            ),
            "memo": (
                "seven little-endian logical pointers at ISO 0x011F010..0x011F01D "
                "resolve in MPR6 bank 0x7F to C01E,C029,C031,C03B,C043,C04F,C059"
            ),
            "source_key": "scene-relative 24-bit offset from the corrected payload start",
        },
        "anomalies": {
            "prefix_underread_ids": sorted(PARTIAL_INLINE_STARTS),
            "prefix_overread_ids": [MEMO_CATALOG_IDS[0]],
            "false_positive_ids": [FALSE_POSITIVE_ID],
        },
        "redirect_index": {
            "status": "NOT_BUILT",
            "reason": (
                "the structural denominator is closed, but three master rows need "
                "boundary repair and the false positive must be removed before "
                "translation encoding/index construction"
            ),
        },
        "outputs": {
            "catalog": OUTPUT_CATALOG.relative_to(ROOT).as_posix(),
            "catalog_sha256": sha256(OUTPUT_CATALOG),
            "report": REPORT.relative_to(ROOT).as_posix(),
        },
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    REPORT.write_text(
        """# Z8.5 field event-bytecode 정적 참조 결과

## 판정

상태는 **STATIC_DENOMINATOR_PASS_BOUNDARY_REPAIR_REQUIRED**다.

기존 236행은 정적으로 다음과 같이 분해된다.

- opcode `02` 인라인 payload: 217행
- opcode `03` 인라인 payload: 10행
- opcode `14` 인라인 payload: 1행
- Memo 16-bit 포인터 테이블: 7행
- 대사로 잘못 검출된 가나 순차표: 1행

따라서 실제 text consumer 분모는 235개이며, 참조 소유자는 전부 열거됐다.
인라인 228개는 명령 바로 뒤의 NUL 종료 payload라 별도 포인터가 없다. Memo 7개는
`0x011F010..0x011F01D`의 little-endian 포인터로 모두 역참조된다.

## 차단된 경계

- `iso:010CAE1`, `iso:010D080`: opcode `02` payload의 앞부분이 master에서 누락됐다.
- `iso:011F011`: 실제 첫 Memo 문자열은 `0x011F01E`인데 master가 포인터 13바이트를
  문자열 앞부분으로 포함했다.
- `iso:010F080`: 가나 순차 lookup table 일부이며 text consumer가 아니다.

정확한 경계를 가진 232행만 현재 redirect 후보가 될 수 있다. 위 3개 경계를
수정하고 false positive를 제거하기 전에는 redirect/index를 만들지 않는다.

이번 단계는 분석 파일만 만들었으며 CUE/BIN/ISO는 변경하지 않았다.
""",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": manifest["status"],
        "input_rows": 236,
        "structural_text_consumers": 235,
        "redirect_eligible_exact_rows": 232,
        "boundary_repairs_required": 3,
        "false_positives": 1,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
