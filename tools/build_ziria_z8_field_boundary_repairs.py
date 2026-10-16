#!/usr/bin/env python3
"""Repair the three proven Z8 field-text boundaries and build its source index.

The global master CSV is intentionally immutable.  The repair overlay records
the corrected structural records, while the generated index is the canonical
235-consumer input for the later Z8 redirect design.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
EVENT_CATALOG = (
    ROOT / "module_relink" / "z8_field_event_refs"
    / "field_event_reference_catalog.csv"
)
REPAIR_CSV = ROOT / "translation" / "ziria_z8_field_boundary_repairs.csv"
INDEX_TSV = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
MANIFEST = ROOT / "translation" / "ziria_z8_field_boundary_repair_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_6_field_boundary_repair_result.md"

MODULE_START = 482 * 2048
MODULE_END = MODULE_START + 96 * 2048
FALSE_POSITIVE_ID = "iso:010F080"

REPAIRS = {
    "iso:010CAE1": {
        "corrected_id": "iso:010CABD",
        "offset": 0x010CABD,
        "original": (
            "とおせんぼするようなやな人は\\n"
            "行きたい方向のキーを押しながらⅡボタンを押すと\\n"
            "すり抜けられるわよ"
        ),
        "translation": (
            "길을 막고 있는 심술궂은 사람이 있으면\\n"
            "가고 싶은 방향 키를 누르면서 II 버튼을 누르면\\n"
            "빠져나갈 수 있어"
        ),
        "action": "PREFIX_UNDERREAD_REPLACED",
        "provenance": (
            "disc opcode-02 boundary + external asset 137479 + "
            "human translation backup"
        ),
    },
    "iso:010D080": {
        "corrected_id": "iso:010D036",
        "offset": 0x010D036,
        "original": (
            "オートバトルはとっても便利だけど\\n"
            "うまく付き合わないと\\n"
            "思わぬ被害を受けるわよ\\p"
            "オートバトルから抜けるには\\n"
            "戦闘中、Ⅱボタンを押し続けてね\\n"
            "フェイトたちのターンが来たら解除されるわ"
        ),
        "translation": (
            "오토 배틀은 정말 편리하지만\\n"
            "잘 활용하지 않으면\\n"
            "생각지도 못한 피해를 입을 수 있어\\p"
            "오토 배틀을 취소하려면\\n"
            "전투 중에 II 버튼을 계속 눌러줘\\n"
            "페이트 일행의 턴이 오면 해제될 거야"
        ),
        "action": "PREFIX_UNDERREAD_REPLACED",
        "provenance": (
            "disc opcode-02 boundary + external assets 146268/146639 + "
            "human translation backup"
        ),
    },
    "iso:011F011": {
        "corrected_id": "iso:011F01E",
        "offset": 0x011F01E,
        "original": "次の目的のこと",
        "translation": "다음 목적지에 대해",
        "action": "POINTER_PREFIX_OVERREAD_REPLACED",
        "provenance": "Memo pointer C01E + translated duplicate family",
    },
}

KANA: dict[str, int] = {}
for _base, _text in (
    (0x28, "ぁあぃいぅうぇえぉお"),
    (0x32, "かがきぎくぐけげこご"),
    (0x3C, "さざしじすずせぜそぞ"),
    (0x46, "ただちぢっつづてでとど"),
    (0x51, "なにぬねの"),
    (0x56, "はばぱひびぴふぶぷへべぺほぼぽ"),
    (0x65, "まみむめも"),
    (0x6A, "ゃやゅゆょよ"),
    (0x70, "らりるれろ"),
    (0x75, "ゎわゐゑをん"),
):
    for _index, _character in enumerate(_text):
        KANA[_character] = _base + _index
HALF2FULL = {
    character: 0xA1 + index
    for index, character in enumerate(
        "。「」、・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソ"
        "タチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"
    )
}
BYTE_TO_KANA = {value: key for key, value in KANA.items()}
BYTE_TO_HALF2FULL = {value: key for key, value in HALF2FULL.items()}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(
            target, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def nul_record(image: bytes, start: int) -> bytes:
    end = image.find(b"\0", start, min(start + 1024, len(image)))
    if end < 0:
        raise ValueError(f"NUL terminator not found at 0x{start:07X}")
    return image[start:end + 1]


def decode_original(raw: bytes) -> str:
    """Decode the game's mixed one-byte-kana/CP932 stream."""
    controls = {0x0C: "\\p", 0x0D: "\\n"}
    # This game's one-byte kana values are Shift-JIS katakana bytes minus 0x72.
    output: list[str] = []
    index = 0
    body = raw[:-1]
    while index < len(body):
        code = body[index]
        if code in controls:
            output.append(controls[code])
            index += 1
        elif code in BYTE_TO_KANA:
            output.append(BYTE_TO_KANA[code])
            index += 1
        elif code in BYTE_TO_HALF2FULL:
            output.append(BYTE_TO_HALF2FULL[code])
            index += 1
        elif (
            (0x81 <= code <= 0x9F or 0xE0 <= code <= 0xEA)
            and index + 1 < len(body)
        ):
            output.append(body[index:index + 2].decode("cp932"))
            index += 2
        else:
            raise ValueError(
                f"unsupported byte 0x{code:02X} at record offset {index}"
            )
    return "".join(output)


def controls(text: str) -> str:
    return " ".join(re.findall(r"\\[np]", text))


def main() -> None:
    for path in (ISO, MASTER, EVENT_CATALOG):
        if not path.is_file():
            raise FileNotFoundError(path)

    image = ISO.read_bytes()
    master = {row["id"]: row for row in read_csv(MASTER)}
    events = read_csv(EVENT_CATALOG)
    if len(events) != 236:
        raise ValueError(f"expected 236 event rows, got {len(events)}")

    repair_rows: list[dict[str, object]] = []
    corrected_by_legacy: dict[str, dict[str, str]] = {}
    for legacy_id, repair in REPAIRS.items():
        old = master[legacy_id]
        start = int(repair["offset"])
        raw = nul_record(image, start)
        decoded = decode_original(raw)
        if decoded != repair["original"]:
            raise ValueError(
                f"corrected original mismatch for {legacy_id}: {decoded!r}"
            )
        row = {
            "legacy_id": legacy_id,
            "corrected_id": repair["corrected_id"],
            "repair_action": repair["action"],
            "legacy_iso_offset": old["iso_offset"],
            "corrected_iso_offset": f"0x{start:07X}",
            "legacy_raw_hex": old["raw_hex"],
            "corrected_raw_hex": raw.hex().upper(),
            "corrected_raw_length": len(raw),
            "original": repair["original"],
            "translation": repair["translation"],
            "controls": controls(repair["original"]),
            "provenance": repair["provenance"],
        }
        repair_rows.append(row)
        corrected_by_legacy[legacy_id] = {
            **old,
            "id": str(repair["corrected_id"]),
            "iso_offset": f"0x{start:07X}",
            "raw_hex": raw.hex().upper(),
            "original": str(repair["original"]),
            "translation": str(repair["translation"]),
            "controls": controls(str(repair["original"])),
        }

    false = master[FALSE_POSITIVE_ID]
    repair_rows.append({
        "legacy_id": FALSE_POSITIVE_ID,
        "corrected_id": "",
        "repair_action": "EXCLUDED_FALSE_POSITIVE",
        "legacy_iso_offset": false["iso_offset"],
        "corrected_iso_offset": "",
        "legacy_raw_hex": false["raw_hex"],
        "corrected_raw_hex": "",
        "corrected_raw_length": 0,
        "original": false["original"],
        "translation": false["translation"],
        "controls": "",
        "provenance": "sequential kana lookup table; no text consumer",
    })
    write_csv(REPAIR_CSV, repair_rows)

    index_rows: list[dict[str, object]] = []
    for event in events:
        legacy_id = event["id"]
        if legacy_id == FALSE_POSITIVE_ID:
            continue
        source_row = corrected_by_legacy.get(legacy_id, master[legacy_id])
        source = int(event["structural_source_iso_offset"], 16)
        if source != int(source_row["iso_offset"], 16):
            raise ValueError(f"structural/master offset mismatch: {legacy_id}")
        raw = bytes.fromhex(source_row["raw_hex"])
        if not raw or raw[-1] != 0 or b"\0" in raw[:-1]:
            raise ValueError(f"invalid corrected record: {legacy_id}")
        if image[source:source + len(raw)] != raw:
            raise ValueError(f"ISO mismatch: {legacy_id}")
        if not MODULE_START <= source < MODULE_END:
            raise ValueError(f"source outside field scene: {legacy_id}")

        module_offset = source - MODULE_START
        physical_bank = 0x68 + module_offset // 0x2000
        bank_offset = module_offset & 0x1FFF
        if not 0x68 <= physical_bank <= 0x7F:
            raise ValueError(f"physical bank outside scene: {legacy_id}")
        index_rows.append({
            "catalogue_position": event["catalogue_position"],
            "legacy_id": legacy_id,
            "id": source_row["id"],
            "source_iso_offset": f"0x{source:07X}",
            "source_module_offset": f"0x{module_offset:05X}",
            "source_key_u24le": module_offset.to_bytes(3, "little").hex().upper(),
            "source_physical_bank": f"0x{physical_bank:02X}",
            "source_bank_offset": f"0x{bank_offset:04X}",
            "reference_kind": event["reference_kind"],
            "reference_storage_iso_offset": event["reference_storage_iso_offset"],
            "reference_raw_hex": event["reference_raw_hex"],
            "raw_length": len(raw),
            "raw_sha256": digest_bytes(raw),
            "raw_hex": raw.hex().upper(),
            "original": source_row["original"],
            "translation": source_row["translation"],
            "controls": source_row["controls"],
            "boundary_status": "REPAIRED" if legacy_id in REPAIRS else "EXACT",
            "runtime_observed": event["runtime_observed"],
        })

    if len(index_rows) != 235:
        raise ValueError(f"expected 235 corrected consumers, got {len(index_rows)}")
    if len({row["id"] for row in index_rows}) != 235:
        raise ValueError("corrected IDs are not unique")
    if len({row["source_key_u24le"] for row in index_rows}) != 235:
        raise ValueError("corrected source keys are not unique")
    write_tsv(INDEX_TSV, index_rows)

    manifest = {
        "format": "ZIRIA-Z8-FIELD-BOUNDARY-REPAIR",
        "version": 1,
        "task": "Z8.6-boundary-repair-and-source-key-index",
        "status": "BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED",
        "mutation_scope": (
            "repair overlay and canonical index only; master_text.csv and "
            "CUE/BIN/ISO remain unmodified"
        ),
        "inputs": {
            "track02_iso": {
                "path": ISO.relative_to(ROOT).as_posix(),
                "sha256": sha256(ISO),
            },
            "master_text": {
                "path": MASTER.relative_to(ROOT).as_posix(),
                "sha256": sha256(MASTER),
                "policy": "immutable baseline",
            },
            "event_catalog": {
                "path": EVENT_CATALOG.relative_to(ROOT).as_posix(),
                "sha256": sha256(EVENT_CATALOG),
            },
        },
        "population": {
            "event_catalog_rows": 236,
            "corrected_text_consumers": 235,
            "exact_rows": 232,
            "repaired_rows": 3,
            "excluded_false_positives": 1,
            "unique_corrected_ids": 235,
            "unique_source_keys": 235,
        },
        "repairs": [
            {
                "legacy_id": row["legacy_id"],
                "corrected_id": row["corrected_id"],
                "action": row["repair_action"],
                "corrected_iso_offset": row["corrected_iso_offset"],
            }
            for row in repair_rows
        ],
        "source_key": {
            "base_iso_offset": f"0x{MODULE_START:07X}",
            "formula": "corrected payload ISO offset - scene base",
            "serialization": "unsigned 24-bit little-endian",
        },
        "outputs": {
            "repair_overlay": REPAIR_CSV.relative_to(ROOT).as_posix(),
            "repair_overlay_sha256": sha256(REPAIR_CSV),
            "source_key_index": INDEX_TSV.relative_to(ROOT).as_posix(),
            "source_key_index_sha256": sha256(INDEX_TSV),
            "report": REPORT.relative_to(ROOT).as_posix(),
        },
        "next_gate": (
            "choose one renderer family and prove its loader-owned redirect/index "
            "byte format against all 235 corrected consumers"
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    REPORT.write_text(
        """# Z8.6 field 경계 보정 및 source-key index 결과

## 판정

**BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED**

- `iso:010CAE1` → `iso:010CABD`: 누락된 이동 통과 안내 prefix 복원
- `iso:010D080` → `iso:010D036`: 누락된 오토 배틀 안내 2페이지 복원
- `iso:011F011` → `iso:011F01E`: Memo 포인터 13바이트 제거
- `iso:010F080`: 가나 lookup table이므로 field 대사 인덱스에서 제외

`master_text.csv`는 기존 매니페스트의 불변 기준이므로 수정하지 않았다.
보정 내용은 overlay CSV에 기록했고, 이후 Z8 설계가 사용할 정본은
235행의 `ziria_z8_field_source_key_index.tsv`다. 보정된 ID와 source key는
각각 235개로 모두 유일하며 모든 raw record가 원본 ISO와 일치한다.

이번 단계에서는 CUE/BIN/ISO를 수정하지 않았다.
""",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": manifest["status"],
        "corrected_text_consumers": 235,
        "exact_rows": 232,
        "repaired_rows": 3,
        "excluded_false_positives": 1,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
