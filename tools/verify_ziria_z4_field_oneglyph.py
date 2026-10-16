#!/usr/bin/env python3
"""Fail-closed static verifier for the Z4 field-local one-glyph build."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z4_field_oneglyph_v3_manifest.json"
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
EXPECTED_ORIGINAL = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
DATA_TRACK_OFFSET = 7_914_480


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def changed_offsets(before: Path, after: Path) -> set[int]:
    result: set[int] = set()
    position = 0
    with before.open("rb") as left, after.open("rb") as right:
        while True:
            a = left.read(4 * 1024 * 1024)
            b = right.read(4 * 1024 * 1024)
            if not a:
                break
            if len(a) != len(b):
                raise AssertionError("compared files have different sizes")
            result.update(position + i for i, (old, new) in enumerate(zip(a, b)) if old != new)
            position += len(a)
    return result


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["status"] in {"STATIC_PASS_RUNTIME_PENDING", "RUNTIME_PASS", "RUNTIME_FAIL"}
    assert digest(ORIGINAL_BIN) == EXPECTED_ORIGINAL
    assert manifest["font"]["glyph"] == "가"
    assert manifest["custom_code"] == "8754"
    assert manifest["hook"]["fallback"] == "unchanged JSR $E060 original BIOS EX_GETFNT"
    assert manifest["hook"]["mpr_changes"] == 0
    assert manifest["hook"]["work_ram_bytes"] == 0

    allowed_physical: set[int] = set()
    changed_sum = 0
    for module in manifest["linked_modules"]:
        source = ROOT / module["input"]
        output = ROOT / module["output"]
        assert digest(source) == module["input_sha256"]
        assert digest(output) == module["output_sha256"]
        offsets = changed_offsets(source, output)
        assert len(offsets) == module["changed_bytes"]
        changed_sum += len(offsets)
        base_lba = 258 if module["id"] == "field.main_engine" else 482
        allowed_physical.update(DATA_TRACK_OFFSET + base_lba * 2048 + x for x in offsets)
        for write in module["writes"]:
            offset = int(write["module_offset"], 16)
            expected = bytes.fromhex(write["expected_hex"])
            replacement = bytes.fromhex(write["replacement_hex"])
            assert source.read_bytes()[offset:offset + len(expected)] == expected
            assert output.read_bytes()[offset:offset + len(replacement)] == replacement

    output_bin = ROOT / manifest["output"]["bin"]
    output_cue = ROOT / manifest["output"]["cue"]
    assert output_bin.stat().st_size == ORIGINAL_BIN.stat().st_size == manifest["output"]["bin_size"]
    assert digest(output_bin) == manifest["output"]["bin_sha256"]
    assert digest(output_cue) == manifest["output"]["cue_sha256"]
    actual = changed_offsets(ORIGINAL_BIN, output_bin)
    assert actual == allowed_physical
    assert len(actual) == changed_sum == manifest["diff_audit"]["actual_changed_bytes"] == 20
    assert manifest["diff_audit"]["audio_changed_bytes"] == 0
    assert manifest["track02"]["loader_tables_changed"] is False
    assert manifest["track02"]["sector_count_preserved"] is True

    registry = json.loads((ROOT / manifest["registry"]).read_text(encoding="utf-8"))
    assert registry["family"] == "field"
    assert len(registry["approved_local_replacements"]) == 2
    assert not registry["external_translation_modules"]
    assert all(x["loader_registration"].startswith("unchanged") for x in registry["approved_local_replacements"])
    assert manifest["hook"]["glyph_physical_bank"] == "0x82"
    assert manifest["hook"]["code_bytes_changed"] == 0
    assert manifest["hook"]["callsite_bytes_changed"] == 0
    assert manifest["hook"]["execution_policy"].startswith("no injected executable code")
    print("PASS: Z4 static module ownership, exact writes, fallback and full-disc diff verified")
    print("changed_modules=2 changed_bytes=20 audio_changes=0 loader_table_changes=0")


if __name__ == "__main__":
    main()
