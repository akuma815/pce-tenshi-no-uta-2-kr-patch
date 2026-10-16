#!/usr/bin/env python3
"""Build the analysis-only Z8 field redirect wire format.

This closes the deterministic on-disc representation for the 235 corrected
field consumers.  It does not allocate an LBA, patch a loader, or mutate an
ISO/CUE/BIN.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import struct
from collections import Counter
from pathlib import Path

from PIL import ImageFont

from build_ziria_z7_glyph_packages import (
    custom_codes,
    pack_expanded_glyph,
    render_glyph,
)
from build_ziria_z8_text_containers import (
    parse_original_body,
    strict_encode,
    token_sequence,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INDEX = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
BOUNDARY_MANIFEST = ROOT / "translation" / "ziria_z8_field_boundary_repair_manifest.json"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
FONT = ROOT / "font" / "Galmuri8x8.ttf"
FONT_POLICY = ROOT / "translation" / "font_build_policy.json"
OUTPUT = ROOT / "module_relink" / "z8_field_redirect_format"
INDEX_BIN = OUTPUT / "field_dialogue_index.bin"
TEXT_BIN = OUTPUT / "field_dialogue_text.bin"
GLYPHS_BIN = OUTPUT / "field_dialogue_glyphs_packed18.bin"
GLYPH_MAP = OUTPUT / "field_dialogue_glyph_map.csv"
RECORDS_TSV = OUTPUT / "field_dialogue_records.tsv"
FORMAT_JSON = OUTPUT / "field_dialogue_format.json"
MANIFEST = ROOT / "translation" / "ziria_z8_field_redirect_format_manifest.json"
REPORT = ROOT / "docs" / "active" / "Z8_7_field_redirect_format_result.md"

EXPECTED_ISO_SHA256 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"
EXPECTED_FONT_SHA256 = "97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05"
SOURCE_BASE = 0x00F1000
BANK = 8192
HEADER_SIZE = 32
RECORD_SIZE = 12
MAGIC = b"Z8FI"
VERSION = 1

KIND = {
    "INLINE_OPCODE_02": 0x01,
    "INLINE_OPCODE_03": 0x02,
    "INLINE_OPCODE_14": 0x03,
    "MEMO_POINTER_TABLE": 0x10,
}
FLAG_RESUME_ORIGINAL = 0x01
FLAG_NATIVE_RETURN = 0x02


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write_csv(path: Path, fields: list[str], rows: list[dict], delimiter: str = ",") -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(
            target, fieldnames=fields, delimiter=delimiter, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def read_rows() -> list[dict]:
    with SOURCE_INDEX.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    if len(rows) != 235:
        raise ValueError(f"expected 235 corrected consumers, got {len(rows)}")
    return rows


def pack_u24(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFF:
        raise ValueError(f"u24 overflow: {value}")
    return value.to_bytes(3, "little")


def main() -> None:
    for path in (SOURCE_INDEX, BOUNDARY_MANIFEST, ISO, FONT, FONT_POLICY):
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha256(ISO) != EXPECTED_ISO_SHA256:
        raise ValueError("Track02_data.iso identity mismatch")
    if sha256(FONT) != EXPECTED_FONT_SHA256:
        raise ValueError("Galmuri8x8 identity mismatch")

    boundary = json.loads(BOUNDARY_MANIFEST.read_text(encoding="utf-8"))
    if boundary["status"] != "BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED":
        raise ValueError("Z8.6 gate is not closed")
    if sha256(SOURCE_INDEX) != boundary["outputs"]["source_key_index_sha256"]:
        raise ValueError("Z8.6 source index identity mismatch")

    policy = json.loads(FONT_POLICY.read_text(encoding="utf-8"))
    if policy["font"]["sha256"] != EXPECTED_FONT_SHA256:
        raise ValueError("font policy identity mismatch")
    font = ImageFont.truetype(
        str(FONT), policy["render_profile"]["loader_size_argument"]
    )

    rows = read_rows()
    iso = ISO.read_bytes()
    glyphs = sorted(
        {
            character
            for row in rows
            for character in row["translation"]
            if "\uac00" <= character <= "\ud7a3"
        }
    )
    codes = custom_codes()
    if len(glyphs) > len(codes):
        raise ValueError(f"{len(glyphs)} glyphs exceed code capacity {len(codes)}")
    glyph_map = {glyph: codes[index].hex().upper() for index, glyph in enumerate(glyphs)}

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    glyph_rows = []
    packed_pool = bytearray()
    for index, glyph in enumerate(glyphs):
        expanded, metric = render_glyph(font, glyph)
        packed = pack_expanded_glyph(expanded)
        packed_pool.extend(packed)
        glyph_rows.append(
            {
                "index": index,
                "character": glyph,
                "unicode": f"U+{ord(glyph):04X}",
                "code": glyph_map[glyph],
                "ink_width": metric["ink_width"],
                "ink_height": metric["ink_height"],
                "advance": metric["advance"],
            }
        )
    GLYPHS_BIN.write_bytes(packed_pool)
    write_csv(GLYPH_MAP, list(glyph_rows[0]), glyph_rows)

    prepared = []
    seen_keys = set()
    for row in rows:
        source_offset = int(row["source_iso_offset"], 16)
        source_key = source_offset - SOURCE_BASE
        serialized_key = bytes.fromhex(row["source_key_u24le"])
        if serialized_key != pack_u24(source_key):
            raise ValueError(f"source key mismatch: {row['id']}")
        if source_key in seen_keys:
            raise ValueError(f"duplicate source key: {row['id']}")
        seen_keys.add(source_key)

        raw = bytes.fromhex(row["raw_hex"])
        raw_length = int(row["raw_length"])
        if len(raw) != raw_length or not raw or raw[-1] != 0:
            raise ValueError(f"invalid raw record: {row['id']}")
        if iso[source_offset:source_offset + raw_length] != raw:
            raise ValueError(f"protected ISO mismatch: {row['id']}")
        if parse_original_body(raw) != token_sequence(row["translation"]):
            raise ValueError(f"control sequence mismatch: {row['id']}")

        translated = strict_encode(row["translation"], glyph_map) + b"\x00"
        if len(translated) > BANK:
            raise ValueError(f"single translated string exceeds 8 KiB: {row['id']}")
        kind = KIND.get(row["reference_kind"])
        if kind is None:
            raise ValueError(f"unsupported reference kind: {row['reference_kind']}")
        flags = (
            FLAG_NATIVE_RETURN
            if row["reference_kind"] == "MEMO_POINTER_TABLE"
            else FLAG_RESUME_ORIGINAL
        )
        prepared.append(
            {
                "row": row,
                "source_key": source_key,
                "raw_length": raw_length,
                "translated": translated,
                "kind": kind,
                "flags": flags,
            }
        )

    prepared.sort(key=lambda item: item["source_key"])
    text_pool = bytearray()
    locations: dict[bytes, int] = {}
    padding_bytes = 0
    for item in prepared:
        translated = item["translated"]
        if translated not in locations:
            inside = len(text_pool) % BANK
            if inside + len(translated) > BANK:
                padding = BANK - inside
                text_pool.extend(b"\xFF" * padding)
                padding_bytes += padding
            locations[translated] = len(text_pool)
            text_pool.extend(translated)
        item["target_offset"] = locations[translated]
        if item["target_offset"] // BANK != (
            item["target_offset"] + len(translated) - 1
        ) // BANK:
            raise ValueError(f"bank crossing: {item['row']['id']}")
    TEXT_BIN.write_bytes(text_pool)

    record_bytes = bytearray()
    record_rows = []
    for ordinal, item in enumerate(prepared):
        row = item["row"]
        translated = item["translated"]
        record = (
            pack_u24(item["source_key"])
            + pack_u24(item["target_offset"])
            + struct.pack("<HHBB", item["raw_length"], len(translated), item["kind"], item["flags"])
        )
        if len(record) != RECORD_SIZE:
            raise AssertionError("record size mismatch")
        record_bytes.extend(record)
        record_rows.append(
            {
                "ordinal": ordinal,
                "id": row["id"],
                "source_key": f"0x{item['source_key']:06X}",
                "source_key_u24le": pack_u24(item["source_key"]).hex().upper(),
                "target_offset": f"0x{item['target_offset']:06X}",
                "target_offset_u24le": pack_u24(item["target_offset"]).hex().upper(),
                "original_length": item["raw_length"],
                "resume_source_key": f"0x{item['source_key'] + item['raw_length']:06X}",
                "translated_length": len(translated),
                "reference_kind": row["reference_kind"],
                "kind_code": f"0x{item['kind']:02X}",
                "flags": f"0x{item['flags']:02X}",
                "translated_sha256": bytes_sha256(translated),
                "boundary_status": row["boundary_status"],
            }
        )

    header = struct.pack(
        "<4sBBHHHIIHHII",
        MAGIC,
        VERSION,
        RECORD_SIZE,
        len(prepared),
        HEADER_SIZE,
        0,
        SOURCE_BASE,
        len(text_pool),
        len(glyphs),
        BANK,
        0,
        0,
    )
    if len(header) != HEADER_SIZE:
        raise AssertionError("header size mismatch")
    INDEX_BIN.write_bytes(header + record_bytes)
    write_csv(RECORDS_TSV, list(record_rows[0]), record_rows, delimiter="\t")

    kind_counts = Counter(row["reference_kind"] for row in rows)
    format_spec = {
        "format": "ZIRIA-Z8-FIELD-REDIRECT-WIRE",
        "version": VERSION,
        "status": "WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN",
        "endianness": "little",
        "header": {
            "size": HEADER_SIZE,
            "struct": "<4sBBHHHIIHHII",
            "fields": [
                "magic", "version", "record_size", "record_count", "header_size",
                "header_flags", "source_base_iso_offset", "text_blob_bytes",
                "glyph_count", "bank_bytes", "reserved0", "reserved1",
            ],
        },
        "record": {
            "size": RECORD_SIZE,
            "fields": [
                {"name": "source_key", "bytes": 3, "meaning": "scene-relative corrected payload offset"},
                {"name": "target_offset", "bytes": 3, "meaning": "relative to field_dialogue_text.bin"},
                {"name": "original_length", "bytes": 2, "meaning": "resume key delta including original NUL"},
                {"name": "translated_length", "bytes": 2, "meaning": "target byte length including regenerated NUL"},
                {"name": "kind", "bytes": 1, "values": KIND},
                {
                    "name": "flags",
                    "bytes": 1,
                    "values": {
                        "0x01": "inline translation NUL resumes source_key + original_length",
                        "0x02": "Memo translation NUL returns through native pointer-string path",
                    },
                },
            ],
        },
        "lookup": {
            "ordering": "strict ascending source_key",
            "algorithm_contract": "exact-match binary search",
            "miss": "use untouched original stream",
            "hit": "use target bytes; continuation selected by flags",
        },
        "text": {
            "terminator": "00 exactly once",
            "bank_bytes": BANK,
            "bank_crossing": "prohibited",
            "padding": "FF outside indexed ranges only",
            "deduplication": "exact encoded byte identity",
        },
        "glyphs": {
            "namespace": "field.dialogue_event unified local namespace",
            "mapping": "sorted Unicode order",
            "custom_code_rule": "EB..EF lead; 40..7E or 80..FC trail",
            "packed_format": "18 bytes: twelve 12-bit rows",
            "font": "font/Galmuri8x8.ttf",
        },
        "runtime_open": [
            "loader-owned sector allocation",
            "field renderer hook entry and live cursor ABI",
            "packed18 load/expand destination lifetime",
            "relocation records and branch reachability",
        ],
        "prohibited_inference": [
            "no Work RAM global pool",
            "no auto sidecar",
            "no shared scene bank persistence",
            "no original text marker bytes",
        ],
    }
    FORMAT_JSON.write_text(
        json.dumps(format_spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    outputs = {
        "index": INDEX_BIN,
        "text": TEXT_BIN,
        "glyphs_packed18": GLYPHS_BIN,
        "glyph_map": GLYPH_MAP,
        "records": RECORDS_TSV,
        "format_spec": FORMAT_JSON,
    }
    manifest = {
        "format": "ZIRIA-Z8-FIELD-REDIRECT-FORMAT-MANIFEST",
        "version": 1,
        "task": "Z8.7-field-redirect-wire-format",
        "status": "WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN",
        "mutation_scope": "analysis-only generated inputs; master_text.csv and CUE/BIN/ISO remain unmodified",
        "inputs": {
            "source_index": {"path": str(SOURCE_INDEX.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(SOURCE_INDEX)},
            "boundary_manifest": {"path": str(BOUNDARY_MANIFEST.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(BOUNDARY_MANIFEST)},
            "track02_iso": {"path": str(ISO.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(ISO)},
            "font": {"path": str(FONT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(FONT)},
        },
        "population": {
            "records": len(prepared),
            "unique_source_keys": len(seen_keys),
            "reference_kinds": dict(sorted(kind_counts.items())),
            "boundary_status": dict(sorted(Counter(row["boundary_status"] for row in rows).items())),
        },
        "wire": {
            "header_bytes": HEADER_SIZE,
            "record_bytes": RECORD_SIZE,
            "index_bytes": len(header) + len(record_bytes),
            "text_bytes": len(text_pool),
            "text_padding_bytes": padding_bytes,
            "unique_translated_strings": len(locations),
            "glyph_count": len(glyphs),
            "glyph_code_capacity": len(codes),
            "glyph_code_margin": len(codes) - len(glyphs),
            "packed_glyph_bytes": len(packed_pool),
            "bank_crossings": 0,
        },
        "outputs": {
            name: {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for name, path in outputs.items()
        },
        "blocked": {
            "disc_build": True,
            "reason": "wire format is closed, but loader-owned allocation and renderer ABI are not yet proven",
        },
        "next_gate": "prove a loader-owned allocation plus field renderer cursor/continuation ABI, then bind this unchanged wire format through explicit relocations",
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report = f"""# Z8.7 field redirect wire format 결과

판정: **WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN**

- Z8.6에서 확정한 235개 corrected consumer를 source key 오름차순으로 직렬화했다.
- 인덱스는 32바이트 헤더와 {RECORD_SIZE}바이트 고정 레코드 {len(prepared)}개로 구성된다.
- 레코드는 source key, 번역 대상, 원문 길이, 번역 길이, consumer kind, continuation flags를 포함한다.
- inline consumer는 번역 NUL 뒤 `source_key + original_length`로 복귀하고, Memo는 native pointer-string return을 사용하도록 형식에서 구분했다.
- 520개 한글을 Galmuri8x8 기반 단일 field-local 코드표로 생성했다(여유 {len(codes) - len(glyphs)}개).
- 문자열 blob은 {len(text_pool)}바이트이며 8 KiB 경계 교차는 0건이다.
- 원문에 마커를 쓰지 않으며 lookup miss는 원문 경로를 그대로 사용한다.

아직 확정하지 않은 것:

- loader-owned sector/LBA 배치
- field renderer hook entry와 실제 cursor/continuation ABI
- packed18 글리프의 적재·확장 목적지와 수명
- relocation 및 branch reachability

따라서 CUE/BIN/ISO는 생성하거나 수정하지 않았다. 다음 게이트는 위 네 항목 중
loader-owned 배치와 renderer ABI를 함께 증명하는 것이다.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(
        f"Z8.7 build PASS: records={len(prepared)} glyphs={len(glyphs)} "
        f"index={INDEX_BIN.stat().st_size} text={TEXT_BIN.stat().st_size}"
    )


if __name__ == "__main__":
    main()
