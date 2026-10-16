#!/usr/bin/env python3
"""Build the combined Z4+Z5 resident battle-text one-glyph PoC.

Runtime tracing proved that first-battle text is read from the resident
field.main_engine (MPR6=$84), not scene.battle_first (LBA 290).  This build
keeps the runtime-passed Z4 $8754 field slot and assigns the original second
local slot $8755/$9192 to the Z5 battle family.  One character in the resident
"%s no attack" message is changed to $8755.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
Z4_DIR = ROOT / "module_relink" / "z4_field_oneglyph_v3_builtin_slot"
Z4_TRACK = Z4_DIR / "Track02_data.z4.iso"
Z4_FIELD = Z4_DIR / "linked_modules" / "field.main_engine_lba0258_s20.bin"
Z4_BIN = Z4_DIR / "output" / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z4_field_oneglyph_v3_builtin_slot.bin"
Z4_CUE = Z4_BIN.with_suffix(".cue")
Z4_MANIFEST = ROOT / "translation" / "ziria_z4_field_oneglyph_v3_manifest.json"

BUILD_DIR = ROOT / "module_relink" / "z5_battle_oneglyph_v1_builtin_slot"
LINKED_DIR = BUILD_DIR / "linked_modules"
OUTPUT_DIR = BUILD_DIR / "output"
TRACK_OUT = BUILD_DIR / "Track02_data.z5.iso"
FIELD_OUT = LINKED_DIR / Z4_FIELD.name
STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z5_battle_oneglyph_v1_builtin_slot"
OUTPUT_BIN = OUTPUT_DIR / f"{STEM}.bin"
OUTPUT_CUE = OUTPUT_DIR / f"{STEM}.cue"
REGISTRY = BUILD_DIR / "extension_registry.json"
MANIFEST = ROOT / "translation" / "ziria_z5_battle_oneglyph_v1_manifest.json"

DATA_TRACK_OFFSET = 7_914_480
FIELD_TRACK_OFFSET = 258 * 2048
EXPECTED_ORIGINAL_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_Z4_TRACK = "9478635F0B66CBB0BFC09F7C7AA7626210C7ACC1A4DD063C27292D3F7A4E1A24"
EXPECTED_Z4_FIELD = "D4092D87DFDBDDCE611B6CDD12676B86A386C1AAA4B2F1F4A9D029693CD7F1E2"
EXPECTED_FONT = "97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05"

SLOT_8755_OFFSET = 0x5192
SLOT_8755_ORIGINAL = bytes.fromhex(
    "00003FC0198019801980198019801980198019803FC000000000000000000000"
)
ATTACK_CODE_OFFSET = 0x96A5
ATTACK_CODE_ORIGINAL = bytes.fromhex("8D55")
ATTACK_CODE_REPLACEMENT = bytes.fromhex("8755")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def changed_ranges(before: bytes, after: bytes) -> tuple[int, list[dict]]:
    if len(before) != len(after):
        raise ValueError("size-changing write rejected")
    ranges: list[list[int]] = []
    count = 0
    for i, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        count += 1
        if ranges and ranges[-1][1] == i:
            ranges[-1][1] += 1
        else:
            ranges.append([i, i + 1])
    return count, [
        {"start": f"0x{s:X}", "end_exclusive": f"0x{e:X}", "changed_bytes": e - s}
        for s, e in ranges
    ]


def patch(image: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> dict:
    if len(expected) != len(replacement):
        raise ValueError(f"length-changing write rejected: {label}")
    actual = bytes(image[offset:offset + len(expected)])
    if actual != expected:
        raise ValueError(f"expected-write mismatch for {label} at 0x{offset:X}: {actual.hex()}")
    image[offset:offset + len(replacement)] = replacement
    return {
        "id": label,
        "module_offset": f"0x{offset:X}",
        "length": len(replacement),
        "expected_hex": expected.hex().upper(),
        "replacement_hex": replacement.hex().upper(),
    }


def copy_span(source, output, length: int) -> None:
    remaining = length
    while remaining:
        block = source.read(min(4 * 1024 * 1024, remaining))
        if not block:
            raise EOFError("short source while rebuilding full BIN")
        output.write(block)
        remaining -= len(block)


def main() -> None:
    if digest(ORIGINAL_BIN) != EXPECTED_ORIGINAL_BIN:
        raise ValueError("original BIN identity mismatch")
    if digest(Z4_TRACK) != EXPECTED_Z4_TRACK or digest(Z4_FIELD) != EXPECTED_Z4_FIELD:
        raise ValueError("runtime-passed Z4 baseline identity mismatch")
    z4 = json.loads(Z4_MANIFEST.read_text(encoding="utf-8"))
    if z4.get("status") != "RUNTIME_PASS":
        raise ValueError("Z4 runtime gate is not PASS")
    if z4["font"]["sha256"] != EXPECTED_FONT:
        raise ValueError("Galmuri8x8 identity mismatch in Z4 manifest")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    field_before = Z4_FIELD.read_bytes()
    field_after = bytearray(field_before)
    glyph = bytes(field_before[0x5172:0x5192])
    writes = [
        patch(field_after, SLOT_8755_OFFSET, SLOT_8755_ORIGINAL, glyph, "battle-local-glyph-8755"),
        patch(field_after, ATTACK_CODE_OFFSET, ATTACK_CODE_ORIGINAL, ATTACK_CODE_REPLACEMENT,
              "battle-attack-message-oneglyph"),
    ]
    FIELD_OUT.write_bytes(field_after)
    z5_field_changed, z5_field_ranges = changed_ranges(field_before, field_after)
    # 13 bytes differ in the 32-byte glyph record.  The two-byte character
    # write 8D55 -> 8755 changes only its lead byte, for a 14-byte net delta.
    if z5_field_changed != 14:
        raise ValueError(f"unexpected Z5 field delta: {z5_field_changed}")

    track_before = Z4_TRACK.read_bytes()
    track_after = bytearray(track_before)
    start = FIELD_TRACK_OFFSET
    end = start + len(field_before)
    if bytes(track_after[start:end]) != field_before:
        raise ValueError("Z4 Track02/field module identity mismatch")
    track_after[start:end] = field_after
    TRACK_OUT.write_bytes(track_after)
    z5_track_changed, z5_track_ranges = changed_ranges(track_before, track_after)
    if z5_track_changed != z5_field_changed:
        raise ValueError("undeclared Track02 changes detected")

    tmp = OUTPUT_BIN.with_suffix(".tmp")
    with Z4_BIN.open("rb") as source, tmp.open("wb") as output:
        copy_span(source, output, DATA_TRACK_OFFSET)
        output.write(track_after)
        source.seek(DATA_TRACK_OFFSET + len(track_before))
        copy_span(source, output, Z4_BIN.stat().st_size - DATA_TRACK_OFFSET - len(track_before))
    tmp.replace(OUTPUT_BIN)

    cue_text = Z4_CUE.read_text(encoding="ascii")
    if cue_text.count(Z4_BIN.name) != 1:
        raise ValueError("Z4 CUE target is ambiguous")
    OUTPUT_CUE.write_text(cue_text.replace(Z4_BIN.name, OUTPUT_BIN.name), encoding="ascii", newline="")

    original_track = ROOT / "module_relink" / "track02" / "Track02_data.identity.iso"
    total_changed, total_ranges = changed_ranges(original_track.read_bytes(), track_after)
    if total_changed != 34:
        raise ValueError(f"unexpected total Z4+Z5 Track02 delta: {total_changed}")
    if OUTPUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
        raise ValueError("full BIN size changed")

    registry = {
        "format": "ZIRIA-Z5-BATTLE-LOCAL-REGISTRY",
        "version": 1,
        "status": "APPROVED_FOR_Z5_RUNTIME_PROBE",
        "family": "battle",
        "renderer_owner": "field.main_engine shared resident renderer",
        "text_owner": "field.main_engine battle text section, traced MPR6=$84",
        "allocations": [
            {"id": "battle-local-glyph-8755", "module_offset": "0x5192", "runtime": "0x9192", "size": 32},
            {"id": "battle-attack-message-oneglyph", "module_offset": "0x96A5", "runtime": "0xD6A5", "size": 2},
        ],
        "prohibited_changes": ["scene.battle_first", "Work RAM code", "BIOS", "MPR logic", "loader table", "audio"],
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "format": "ZIRIA-Z5-BATTLE-ONEGLYPH",
        "version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "baseline": {"id": "Z4 v3", "manifest": str(Z4_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
                     "status": z4["status"]},
        "runtime_trace_finding": {
            "getfnt_call": "0x967E MPR4=$82",
            "stream_reader": "$4036 -> $42AB/$42BA",
            "battle_text_range": "MPR6=$84 physical $108ADA-$109F67",
            "scene_battle_first_reads": 0,
        },
        "font": {"path": "font/Galmuri8x8.ttf", "sha256": EXPECTED_FONT, "glyph": "가"},
        "custom_code": "8755",
        "field_module": {
            "input": str(Z4_FIELD.relative_to(ROOT)).replace("\\", "/"),
            "input_sha256": digest(Z4_FIELD),
            "output": str(FIELD_OUT.relative_to(ROOT)).replace("\\", "/"),
            "output_sha256": digest(FIELD_OUT),
            "z5_changed_bytes": z5_field_changed,
            "z5_changed_ranges": z5_field_ranges,
            "writes": writes,
        },
        "track02": {
            "output": str(TRACK_OUT.relative_to(ROOT)).replace("\\", "/"),
            "output_sha256": digest(TRACK_OUT),
            "z5_changed_bytes": z5_track_changed,
            "z5_changed_ranges": z5_track_ranges,
            "total_z4_z5_changed_bytes": total_changed,
            "total_z4_z5_changed_ranges": total_ranges,
            "sector_count_preserved": True,
        },
        "output": {
            "bin": str(OUTPUT_BIN.relative_to(ROOT)).replace("\\", "/"),
            "bin_size": OUTPUT_BIN.stat().st_size,
            "bin_sha256": digest(OUTPUT_BIN),
            "cue": str(OUTPUT_CUE.relative_to(ROOT)).replace("\\", "/"),
            "cue_sha256": digest(OUTPUT_CUE),
        },
        "diff_audit": {
            "scene_battle_first_changed_bytes": 0,
            "code_changed_bytes": 0,
            "mpr_changes": 0,
            "work_ram_bytes": 0,
            "loader_table_changes": 0,
            "audio_changed_bytes": 0,
            "cue_track_layout_changed": False,
        },
        "runtime": {
            "status": "PENDING",
            "required_checks": [
                "field Z4 custom glyph still renders 가",
                "Memo enters and returns normally",
                "first battle attack message contains one 가 glyph",
                "attack resolves and returns to the field",
                "tower entry after battle remains normal",
                "field character graphics remain normal",
            ],
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS Z5 delta bytes: {z5_track_changed}")
    print(f"PASS total Z4+Z5 delta bytes: {total_changed}")
    print(OUTPUT_CUE)
    print(MANIFEST)


if __name__ == "__main__":
    main()
