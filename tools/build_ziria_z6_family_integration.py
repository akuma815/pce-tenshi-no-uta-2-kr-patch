#!/usr/bin/env python3
"""Build the Z6 transition-family integration gate on the runtime-passed Z5.

The Z6 traces prove that field, Memo, battle, tower, and portrait/event all use
the same resident GETFNT renderer.  This build therefore adds no renderer or
loader code.  It reuses the Z4 $8754 ``ga`` glyph and replaces two one-byte
tokens with the fixed-length raw code 87 54 in each traced scene source.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
IDENTITY_TRACK = ROOT / "module_relink/track02/Track02_data.identity.iso"
Z5_DIR = ROOT / "module_relink/z5_battle_oneglyph_v1_builtin_slot"
Z5_TRACK = Z5_DIR / "Track02_data.z5.iso"
Z5_BIN = Z5_DIR / "output/Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z5_battle_oneglyph_v1_builtin_slot.bin"
Z5_CUE = Z5_BIN.with_suffix(".cue")
Z5_MANIFEST = ROOT / "translation/ziria_z5_battle_oneglyph_v1_manifest.json"

BUILD_DIR = ROOT / "module_relink/z6_family_integration_v1_shared_slot"
LINKED_DIR = BUILD_DIR / "linked_modules"
OUTPUT_DIR = BUILD_DIR / "output"
TRACK_OUT = BUILD_DIR / "Track02_data.z6.iso"
FIELD_OUT = LINKED_DIR / "scene.field_start_lba0482_s96.bin"
TOWER_OUT = LINKED_DIR / "scene.tower_first_lba2882_s96.bin"
STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_family_integration_v1_shared_slot"
OUTPUT_BIN = OUTPUT_DIR / f"{STEM}.bin"
OUTPUT_CUE = OUTPUT_DIR / f"{STEM}.cue"
REGISTRY = BUILD_DIR / "extension_registry.json"
MANIFEST = ROOT / "translation/ziria_z6_family_integration_v1_manifest.json"

DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
FIELD_LBA, FIELD_SECTORS = 482, 96
TOWER_LBA, TOWER_SECTORS = 2882, 96
EXPECTED_ORIGINAL_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_Z5_TRACK = "042663D35A2F4E2C7236D5741AAB68E5893191E525EE405A1A8EAFA1D925B5C3"
EXPECTED_Z5_BIN = "7E133A82ECA649535534C9FF3D563BA801DDBBB6625014542A430901E3C0932A"
EXPECTED_FONT = "97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05"

RAW_GA = bytes.fromhex("8754")
PATCHES = [
    # (owner, absolute Track02 offset, expected two one-byte tokens)
    ("memo-field-speaker-name-shio", 0x011FA17, bytes.fromhex("BCB5")),
    ("tower-dialogue-speaker-name-fe", 0x05BA0EC, bytes.fromhex("CCAA")),
    ("portrait-event-speaker-name-shio", 0x05BA1AF, bytes.fromhex("BCB5")),
    ("memo-tower-copy-speaker-name-shio", 0x05BDA17, bytes.fromhex("BCB5")),
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
    if digest(Z5_TRACK) != EXPECTED_Z5_TRACK or digest(Z5_BIN) != EXPECTED_Z5_BIN:
        raise ValueError("runtime-passed Z5 baseline identity mismatch")
    z5 = json.loads(Z5_MANIFEST.read_text(encoding="utf-8"))
    if z5.get("status") != "RUNTIME_PASS" or z5["runtime"]["status"] != "PASS":
        raise ValueError("Z5 runtime gate is not PASS")
    if z5["font"]["sha256"] != EXPECTED_FONT:
        raise ValueError("Galmuri8x8 identity mismatch")

    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    before = Z5_TRACK.read_bytes()
    after = bytearray(before)
    writes = [patch(after, offset, expected, RAW_GA, owner) for owner, offset, expected in PATCHES]
    z6_changed, z6_ranges = changed_ranges(before, after)
    if z6_changed != 8 or len(z6_ranges) != 4:
        raise ValueError(f"unexpected Z6 delta: bytes={z6_changed}, ranges={len(z6_ranges)}")
    TRACK_OUT.write_bytes(after)

    FIELD_OUT.write_bytes(module_slice(after, FIELD_LBA, FIELD_SECTORS))
    TOWER_OUT.write_bytes(module_slice(after, TOWER_LBA, TOWER_SECTORS))

    tmp = OUTPUT_BIN.with_suffix(".tmp")
    with Z5_BIN.open("rb") as source, tmp.open("wb") as output:
        copy_span(source, output, DATA_TRACK_OFFSET)
        output.write(after)
        source.seek(DATA_TRACK_OFFSET + len(before))
        copy_span(source, output, Z5_BIN.stat().st_size - DATA_TRACK_OFFSET - len(before))
    tmp.replace(OUTPUT_BIN)

    cue_text = Z5_CUE.read_text(encoding="ascii")
    if cue_text.count(Z5_BIN.name) != 1:
        raise ValueError("Z5 CUE target is ambiguous")
    OUTPUT_CUE.write_text(cue_text.replace(Z5_BIN.name, OUTPUT_BIN.name), encoding="ascii", newline="")

    total_changed, total_ranges = changed_ranges(IDENTITY_TRACK.read_bytes(), after)
    if total_changed != 42:
        raise ValueError(f"unexpected total Z4+Z5+Z6 delta: {total_changed}")
    if OUTPUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
        raise ValueError("full BIN size changed")

    registry = {
        "format": "ZIRIA-Z6-FAMILY-INTEGRATION-REGISTRY",
        "version": 1,
        "status": "APPROVED_FOR_Z6_RUNTIME_PROBE",
        "renderer_owner": "field.main_engine shared resident renderer at $967E/MPR4=$82",
        "shared_glyph": {"code": "8754", "record": "$9172", "glyph": "가"},
        "scene_writes": writes,
        "prohibited_changes": [
            "renderer code", "glyph records", "battle module", "Work RAM", "BIOS",
            "MPR logic", "loader table", "audio", "CUE track layout"
        ],
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "format": "ZIRIA-Z6-FAMILY-INTEGRATION",
        "version": 1,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "baseline": {
            "id": "Z5 battle one-glyph v1",
            "manifest": str(Z5_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "status": z5["status"],
            "bin_sha256": EXPECTED_Z5_BIN,
        },
        "trace_evidence": {
            "transition_trace": "translation/ziria_z6_family_transition_trace.tsv",
            "source_trace": "translation/ziria_z6_stream_source_trace.tsv",
            "shared_getfnt": "$967E with MPR4=$82",
            "field_scene": "LBA482, MPR $68-$7F",
            "tower_scene": "LBA2882, MPR $68-$7F",
        },
        "font": {"path": "font/Galmuri8x8.ttf", "sha256": EXPECTED_FONT, "glyph": "가"},
        "custom_code": "8754",
        "writes": writes,
        "linked_modules": {
            "scene.field_start": {"output": str(FIELD_OUT.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(FIELD_OUT)},
            "scene.tower_first": {"output": str(TOWER_OUT.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(TOWER_OUT)},
        },
        "track02": {
            "output": str(TRACK_OUT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest(TRACK_OUT),
            "z6_changed_bytes": z6_changed,
            "z6_changed_ranges": z6_ranges,
            "total_z4_z5_z6_changed_bytes": total_changed,
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
            "z6_scene_source_changed_bytes": 8,
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
                "first field dialogue still renders the Z4 ga glyph",
                "Memo in the first field has ga in the speaker name and returns normally",
                "first battle attack ga glyph and field return remain normal",
                "tower entry after battle remains normal",
                "tower dialogue has ga in the speaker name",
                "tower portrait/event has ga in the speaker name",
                "Memo inside the tower has ga in the speaker name and returns normally",
                "field characters and portrait graphics remain normal",
            ],
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS Z6 incremental bytes: {z6_changed}")
    print(f"PASS total Z4+Z5+Z6 bytes: {total_changed}")
    print(OUTPUT_CUE)
    print(MANIFEST)


if __name__ == "__main__":
    main()
