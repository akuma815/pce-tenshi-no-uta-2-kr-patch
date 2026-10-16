#!/usr/bin/env python3
"""Build corrected Z6.1 v2 body-consumer gate on runtime-passed Z6.

v1 selected the later portrait/event record at 0x05BA1AD.  Runtime evidence
showed that the first dialogue displayed after entering the tower is the
record at 0x05BA0EA.  v2 starts again from Z6, keeps the verified Memo-body
probe, and moves the tower-body probe to the actual ``#1`` consumer.
"""

from __future__ import annotations

import json
from pathlib import Path

from build_ziria_z6_1_body_consumers import (
    copy_span,
    changed_ranges,
    digest,
    module_slice,
    patch,
)


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
IDENTITY_TRACK = ROOT / "module_relink/track02/Track02_data.identity.iso"
Z6_DIR = ROOT / "module_relink/z6_family_integration_v1_shared_slot"
Z6_TRACK = Z6_DIR / "Track02_data.z6.iso"
Z6_BIN = Z6_DIR / "output/Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_family_integration_v1_shared_slot.bin"
Z6_CUE = Z6_BIN.with_suffix(".cue")
Z6_MANIFEST = ROOT / "translation/ziria_z6_family_integration_v1_manifest.json"

BUILD_DIR = ROOT / "module_relink/z6_1_body_consumers_v2_shared_slot"
LINKED_DIR = BUILD_DIR / "linked_modules"
OUTPUT_DIR = BUILD_DIR / "output"
TRACK_OUT = BUILD_DIR / "Track02_data.z6_1_v2.iso"
FIELD_OUT = LINKED_DIR / "scene.field_start_lba0482_s96.bin"
TOWER_OUT = LINKED_DIR / "scene.tower_first_lba2882_s96.bin"
STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_1_body_consumers_v2_shared_slot"
OUTPUT_BIN = OUTPUT_DIR / f"{STEM}.bin"
OUTPUT_CUE = OUTPUT_DIR / f"{STEM}.cue"
REGISTRY = BUILD_DIR / "extension_registry.json"
MANIFEST = ROOT / "translation/ziria_z6_1_body_consumers_v2_manifest.json"

DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048
FIELD_LBA, FIELD_SECTORS = 482, 96
TOWER_LBA, TOWER_SECTORS = 2882, 96
EXPECTED_ORIGINAL_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_Z6_TRACK = "ADC6E878EECB6CCECA2D3CDE92A32782B40743882E8CEC994138CD310254AD41"
EXPECTED_Z6_BIN = "D598B992BA0118641639BD811772CF17BF309C1B4D090C50E21E295DE28DF18E"

RAW_GA = bytes.fromhex("8754")
PATCHES = [
    ("memo-field-dialogue-body-first-code", 0x011FA1F, bytes.fromhex("9595")),
    # Record 0x05BA0EA:
    #   #5 フェイト ： CR #1 47 68 47 ...
    # Runtime screenshot identifies this as the first post-entry tower line.
    ("tower-post-entry-first-dialogue-body-code", 0x05BA0F5, bytes.fromhex("4768")),
]


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
            f"unexpected Z6.1 v2 delta: bytes={incremental_changed}, ranges={len(incremental_ranges)}"
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
        raise ValueError(f"unexpected total Z4+Z5+Z6+Z6.1 v2 delta: {total_changed}")
    if OUTPUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
        raise ValueError("full BIN size changed")

    registry = {
        "format": "ZIRIA-Z6.1-BODY-CONSUMER-REGISTRY",
        "version": 2,
        "status": "APPROVED_FOR_Z6.1_V2_RUNTIME_PROBE",
        "baseline": "runtime-passed Z6 (v1 body probe is not inherited)",
        "renderer_owner": "field.main_engine shared resident renderer at $967E/MPR4=$82",
        "shared_glyph": {"code": "8754", "record": "$9172", "glyph": "가"},
        "scene_writes": writes,
        "rejected_v1_target": {
            "track02_offset": "0x5BA1B7",
            "reason": "later portrait/event body, not first post-entry tower dialogue",
        },
        "prohibited_changes": [
            "speaker names", "renderer code", "glyph records", "battle module",
            "Work RAM", "BIOS", "MPR logic", "loader table", "audio",
            "CUE track layout", "control codes", "stream lengths",
        ],
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "format": "ZIRIA-Z6.1-BODY-CONSUMERS",
        "version": 2,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "baseline": {
            "id": "Z6 family integration v1",
            "manifest": str(Z6_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "status": z6["status"],
            "bin_sha256": EXPECTED_Z6_BIN,
            "track02_sha256": EXPECTED_Z6_TRACK,
        },
        "correction": {
            "v1_result": "PARTIAL_PASS_WRONG_TOWER_BODY_TARGET",
            "rejected_target": "0x5BA1B7",
            "runtime_observed_record": "0x5BA0EA",
            "corrected_body_offset": "0x5BA0F5",
            "evidence": [
                "runtime screenshot: speaker name begins with ga but body remains original",
                "master_text.csv record iso:05BA0EA",
                "raw bytes place #1 at 0x5BA0F3 and body at 0x5BA0F5",
            ],
        },
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
            "v1_wrong_target_bytes_inherited": 0,
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
            "known_pass_from_v1": [
                "first-field Memo body ga and normal return",
                "battle and post-battle field return",
                "tower entry",
                "portrait and character graphics",
            ],
            "required_checks": [
                "first post-entry tower dialogue body begins with ga",
                "remaining body text, page state, and event progression remain normal",
                "no black screen, invalid field transition, freeze, or EXEC BRK loop",
            ],
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"PASS Z6.1 v2 incremental bytes: {incremental_changed}")
    print(f"PASS total Z4+Z5+Z6+Z6.1 v2 bytes: {total_changed}")
    print(OUTPUT_CUE)
    print(MANIFEST)


if __name__ == "__main__":
    main()
