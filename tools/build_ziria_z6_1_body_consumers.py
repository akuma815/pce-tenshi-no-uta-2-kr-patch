#!/usr/bin/env python3
"""Build the Z6.1 Memo/tower dialogue-body consumer gate on runtime-passed Z6.

Z6 proved that the four scene families can consume the existing field-local
$8754 glyph from speaker-name streams.  Z6.1 changes only the first actual
body code in two representative consumers:

* the first-field Memo record after ``#1``;
* the tower-entry portrait/dialogue record after ``#1``.

No renderer, glyph, loader, pointer, control code, or stream length changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
IDENTITY_TRACK = ROOT / "module_relink/track02/Track02_data.identity.iso"
Z6_DIR = ROOT / "module_relink/z6_family_integration_v1_shared_slot"
Z6_TRACK = Z6_DIR / "Track02_data.z6.iso"
Z6_BIN = Z6_DIR / "output/Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_family_integration_v1_shared_slot.bin"
Z6_CUE = Z6_BIN.with_suffix(".cue")
Z6_MANIFEST = ROOT / "translation/ziria_z6_family_integration_v1_manifest.json"

BUILD_DIR = ROOT / "module_relink/z6_1_body_consumers_v1_shared_slot"
LINKED_DIR = BUILD_DIR / "linked_modules"
OUTPUT_DIR = BUILD_DIR / "output"
TRACK_OUT = BUILD_DIR / "Track02_data.z6_1.iso"
FIELD_OUT = LINKED_DIR / "scene.field_start_lba0482_s96.bin"
TOWER_OUT = LINKED_DIR / "scene.tower_first_lba2882_s96.bin"
STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_1_body_consumers_v1_shared_slot"
OUTPUT_BIN = OUTPUT_DIR / f"{STEM}.bin"
OUTPUT_CUE = OUTPUT_DIR / f"{STEM}.cue"
REGISTRY = BUILD_DIR / "extension_registry.json"
MANIFEST = ROOT / "translation/ziria_z6_1_body_consumers_v1_manifest.json"

DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
FIELD_LBA, FIELD_SECTORS = 482, 96
TOWER_LBA, TOWER_SECTORS = 2882, 96
EXPECTED_ORIGINAL_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_Z6_TRACK = "ADC6E878EECB6CCECA2D3CDE92A32782B40743882E8CEC994138CD310254AD41"
EXPECTED_Z6_BIN = "D598B992BA0118641639BD811772CF17BF309C1B4D090C50E21E295DE28DF18E"

RAW_GA = bytes.fromhex("8754")
PATCHES = [
    # Z5/Z6 bytes around this location:
    #   #5 シオン ： CR #1 95 95 ...
    # Replace the first two compressed body tokens after #1 with one raw code.
    ("memo-field-dialogue-body-first-code", 0x011FA1F, bytes.fromhex("9595")),
    # Extracted record 0x05BA1AD:
    #   #5 シオン ： CR #1 81 45 81 45 81 45 ...
    # Replace only the first raw SJIS ellipsis after #1.
    ("tower-entry-dialogue-body-first-code", 0x05BA1B7, bytes.fromhex("8145")),
]


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
        raise ValueError(f"expected-write mismatch {label} at 0x{offset:X}: {actual.hex()}")
    image[offset:offset + len(replacement)] = replacement
    return {
        "id": label,
        "track02_offset": f"0x{offset:X}",
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


def module_slice(track: bytes, lba: int, sectors: int) -> bytes:
    start = lba * SECTOR
    return track[start:start + sectors * SECTOR]


def main() -> None:
    if digest(ORIGINAL_BIN) != EXPECTED_ORIGINAL_BIN:
        raise ValueError("original BIN identity mismatch")
    if digest(Z6_TRACK) != EXPECTED_Z6_TRACK or digest(Z6_BIN) != EXPECTED_Z6_BIN:
        raise ValueError("runtime-passed Z6 baseline identity mismatch")
    z6 = json.loads(Z6_MANIFEST.read_text(encoding="utf-8"))
    if z6.get("status") != "RUNTIME_PASS" or z6["runtime"]["status"] != "PASS":
        raise ValueError("Z6 runtime gate is not PASS")

    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    before = Z6_TRACK.read_bytes()
    after = bytearray(before)
    writes = [patch(after, offset, expected, RAW_GA, label) for label, offset, expected in PATCHES]
    incremental_changed, incremental_ranges = changed_ranges(before, after)
    if incremental_changed != 4 or len(incremental_ranges) != 2:
        raise ValueError(
            f"unexpected Z6.1 delta: bytes={incremental_changed}, ranges={len(incremental_ranges)}"
        )
    TRACK_OUT.write_bytes(after)

    FIELD_OUT.write_bytes(module_slice(after, FIELD_LBA, FIELD_SECTORS))
    TOWER_OUT.write_bytes(module_slice(after, TOWER_LBA, TOWER_SECTORS))

    tmp = OUTPUT_BIN.with_suffix(".tmp")
    with Z6_BIN.open("rb") as source, tmp.open("wb") as output:
        copy_span(source, output, DATA_TRACK_OFFSET)
        output.write(after)
        source.seek(DATA_TRACK_OFFSET + len(before))
        copy_span(source, output, Z6_BIN.stat().st_size - DATA_TRACK_OFFSET - len(before))
    tmp.replace(OUTPUT_BIN)

    cue_text = Z6_CUE.read_text(encoding="ascii")
    if cue_text.count(Z6_BIN.name) != 1:
        raise ValueError("Z6 CUE target is ambiguous")
    OUTPUT_CUE.write_text(cue_text.replace(Z6_BIN.name, OUTPUT_BIN.name), encoding="ascii", newline="")

    total_changed, total_ranges = changed_ranges(IDENTITY_TRACK.read_bytes(), after)
    if total_changed != 46:
        raise ValueError(f"unexpected total Z4+Z5+Z6+Z6.1 delta: {total_changed}")
    if OUTPUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
        raise ValueError("full BIN size changed")

    registry = {
        "format": "ZIRIA-Z6.1-BODY-CONSUMER-REGISTRY",
        "version": 1,
        "status": "APPROVED_FOR_Z6.1_RUNTIME_PROBE",
        "baseline": "runtime-passed Z6",
        "renderer_owner": "field.main_engine shared resident renderer at $967E/MPR4=$82",
        "shared_glyph": {"code": "8754", "record": "$9172", "glyph": "가"},
        "scene_writes": writes,
        "prohibited_changes": [
            "speaker names", "renderer code", "glyph records", "battle module",
            "Work RAM", "BIOS", "MPR logic", "loader table", "audio",
            "CUE track layout", "control codes", "stream lengths",
        ],
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "format": "ZIRIA-Z6.1-BODY-CONSUMERS",
        "version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "baseline": {
            "id": "Z6 family integration v1",
            "manifest": str(Z6_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "status": z6["status"],
            "bin_sha256": EXPECTED_Z6_BIN,
            "track02_sha256": EXPECTED_Z6_TRACK,
        },
        "purpose": [
            "close the untested first-field Memo dialogue-body consumer",
            "close the untested tower-entry dialogue-body consumer",
        ],
        "font": z6["font"],
        "custom_code": "8754",
        "writes": writes,
        "linked_modules": {
            "scene.field_start": {
                "output": str(FIELD_OUT.relative_to(ROOT)).replace("\\", "/"),
                "sha256": digest(FIELD_OUT),
            },
            "scene.tower_first": {
                "output": str(TOWER_OUT.relative_to(ROOT)).replace("\\", "/"),
                "sha256": digest(TOWER_OUT),
            },
        },
        "track02": {
            "output": str(TRACK_OUT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest(TRACK_OUT),
            "incremental_changed_bytes": incremental_changed,
            "incremental_changed_ranges": incremental_ranges,
            "total_z4_z5_z6_z6_1_changed_bytes": total_changed,
            "total_ranges": total_ranges,
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
            "incremental_scene_source_changed_bytes": 4,
            "speaker_name_changed_bytes": 0,
            "control_code_changed_bytes": 0,
            "code_changed_bytes": 0,
            "glyph_record_changed_bytes": 0,
            "battle_module_changed_bytes": 0,
            "mpr_changes": 0,
            "work_ram_bytes": 0,
            "loader_table_changes": 0,
            "audio_changed_bytes": 0,
            "cue_track_layout_changed": False,
        },
        "runtime": {
            "status": "PENDING",
            "required_checks": [
                "first field dialogue body still renders ga",
                "first-field Memo body begins with ga and Memo returns normally",
                "first battle attack and field return remain normal",
                "tower entry after battle remains normal",
                "tower-entry dialogue body begins with ga",
                "portrait and character graphics remain normal",
                "no black screen, invalid field transition, freeze, or EXEC BRK loop",
            ],
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"PASS Z6.1 incremental bytes: {incremental_changed}")
    print(f"PASS total Z4+Z5+Z6+Z6.1 bytes: {total_changed}")
    print(OUTPUT_CUE)
    print(MANIFEST)


if __name__ == "__main__":
    main()
