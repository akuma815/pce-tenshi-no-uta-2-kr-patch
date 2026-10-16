#!/usr/bin/env python3
"""Independently verify the Z8.7 field redirect wire-format artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from build_ziria_z8_text_containers import (
    parse_original_body,
    strict_encode,
    token_sequence,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "translation" / "ziria_z8_field_source_key_index.tsv"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
OUT = ROOT / "module_relink" / "z8_field_redirect_format"
INDEX = OUT / "field_dialogue_index.bin"
TEXT = OUT / "field_dialogue_text.bin"
GLYPHS = OUT / "field_dialogue_glyphs_packed18.bin"
GLYPH_MAP = OUT / "field_dialogue_glyph_map.csv"
RECORDS = OUT / "field_dialogue_records.tsv"
FORMAT = OUT / "field_dialogue_format.json"
MANIFEST = ROOT / "translation" / "ziria_z8_field_redirect_format_manifest.json"

MAGIC = b"Z8FI"
HEADER_SIZE = 32
RECORD_SIZE = 12
BANK = 8192
SOURCE_BASE = 0x00F1000
KIND = {
    "INLINE_OPCODE_02": 0x01,
    "INLINE_OPCODE_03": 0x02,
    "INLINE_OPCODE_14": 0x03,
    "MEMO_POINTER_TABLE": 0x10,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def u24(data: bytes) -> int:
    require(len(data) == 3, "u24 width")
    return int.from_bytes(data, "little")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest["status"] == "WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN",
        "manifest status",
    )
    require(manifest["blocked"]["disc_build"] is True, "disc build must remain blocked")
    for item in manifest["outputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"missing output: {path}")
        require(path.stat().st_size == item["bytes"], f"size: {path.name}")
        require(sha256(path) == item["sha256"], f"hash: {path.name}")

    with SOURCE.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    with GLYPH_MAP.open("r", encoding="utf-8-sig", newline="") as source:
        glyph_rows = list(csv.DictReader(source))
    with RECORDS.open("r", encoding="utf-8-sig", newline="") as source:
        record_rows = list(csv.DictReader(source, delimiter="\t"))
    require(len(rows) == len(record_rows) == 235, "record population")
    require(len(glyph_rows) == 520, "glyph population")
    require(GLYPHS.stat().st_size == len(glyph_rows) * 18, "packed glyph size")

    glyph_map = {row["character"]: row["code"] for row in glyph_rows}
    require(len(glyph_map) == len(glyph_rows), "glyph map uniqueness")
    require(
        [row["character"] for row in glyph_rows] == sorted(glyph_map),
        "glyph Unicode ordering",
    )
    require(len(set(glyph_map.values())) == len(glyph_map), "glyph code uniqueness")

    index = INDEX.read_bytes()
    text = TEXT.read_bytes()
    require(len(index) >= HEADER_SIZE, "index header")
    header = struct.unpack("<4sBBHHHIIHHII", index[:HEADER_SIZE])
    (
        magic, version, record_size, count, header_size, header_flags,
        source_base, text_bytes, glyph_count, bank_bytes, reserved0, reserved1,
    ) = header
    require(magic == MAGIC and version == 1, "header identity")
    require(record_size == RECORD_SIZE and header_size == HEADER_SIZE, "header sizes")
    require(count == 235, "header count")
    require(header_flags == reserved0 == reserved1 == 0, "reserved fields")
    require(source_base == SOURCE_BASE, "source base")
    require(text_bytes == len(text), "text size")
    require(glyph_count == len(glyph_rows), "header glyph count")
    require(bank_bytes == BANK, "bank size")
    require(len(index) == HEADER_SIZE + count * RECORD_SIZE, "index exact size")

    iso = ISO.read_bytes()
    source_by_key = {}
    for row in rows:
        source_offset = int(row["source_iso_offset"], 16)
        key = source_offset - SOURCE_BASE
        require(key not in source_by_key, f"duplicate source key: {row['id']}")
        source_by_key[key] = row
        raw = bytes.fromhex(row["raw_hex"])
        require(iso[source_offset:source_offset + len(raw)] == raw, f"ISO raw: {row['id']}")
        require(parse_original_body(raw) == token_sequence(row["translation"]), f"tokens: {row['id']}")

    previous_key = -1
    seen_targets = set()
    kind_counts = Counter()
    for ordinal in range(count):
        start = HEADER_SIZE + ordinal * RECORD_SIZE
        record = index[start:start + RECORD_SIZE]
        key = u24(record[0:3])
        target = u24(record[3:6])
        original_length, translated_length, kind, flags = struct.unpack("<HHBB", record[6:12])
        require(key > previous_key, f"strict key ordering: {ordinal}")
        previous_key = key
        require(key in source_by_key, f"unknown source key: {key:06X}")
        row = source_by_key[key]
        require(original_length == int(row["raw_length"]), f"original length: {row['id']}")
        require(kind == KIND[row["reference_kind"]], f"kind: {row['id']}")
        expected_flags = 0x02 if row["reference_kind"] == "MEMO_POINTER_TABLE" else 0x01
        require(flags == expected_flags, f"flags: {row['id']}")
        require(0 < translated_length <= BANK, f"translated length: {row['id']}")
        require(target + translated_length <= len(text), f"target range: {row['id']}")
        require(target // BANK == (target + translated_length - 1) // BANK, f"bank crossing: {row['id']}")
        translated = text[target:target + translated_length]
        require(translated[-1] == 0 and b"\x00" not in translated[:-1], f"NUL policy: {row['id']}")
        expected = strict_encode(row["translation"], glyph_map) + b"\x00"
        require(translated == expected, f"encoded bytes: {row['id']}")
        require(
            int(record_rows[ordinal]["source_key"], 16) == key
            and int(record_rows[ordinal]["target_offset"], 16) == target,
            f"record TSV binding: {row['id']}",
        )
        require(
            int(record_rows[ordinal]["resume_source_key"], 16) == key + original_length,
            f"resume key: {row['id']}",
        )
        seen_targets.add((target, translated_length))
        kind_counts[row["reference_kind"]] += 1

    require(set(source_by_key) == {
        u24(index[HEADER_SIZE + n * RECORD_SIZE:HEADER_SIZE + n * RECORD_SIZE + 3])
        for n in range(count)
    }, "source denominator closure")
    require(dict(sorted(kind_counts.items())) == manifest["population"]["reference_kinds"], "kind counts")
    spec = json.loads(FORMAT.read_text(encoding="utf-8"))
    require(spec["record"]["size"] == RECORD_SIZE, "format record size")
    require(spec["lookup"]["miss"] == "use untouched original stream", "fallback contract")
    require(len(seen_targets) == manifest["wire"]["unique_translated_strings"], "dedup targets")
    require(manifest["wire"]["bank_crossings"] == 0, "manifest bank crossing")
    print(
        f"Z8.7 verification PASS: records={count} glyphs={len(glyph_rows)} "
        f"index={len(index)} text={len(text)}"
    )


if __name__ == "__main__":
    main()
