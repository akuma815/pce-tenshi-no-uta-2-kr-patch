#!/usr/bin/env python3
"""Build Z4 v3 using the original field renderer's built-in local glyph slot.

Only two loader-owned modules are changed:
* field.main_engine: replace the existing $8754 local 32-byte glyph record
* scene.field_start: one original two-byte character becomes code $8754

No Work RAM code, sidecar load, BIOS patch, MPR change, or cross-family state is
introduced.  The build starts from Z2 identity artifacts and emits a new CUE/BIN.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
ORIGINAL_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
Z2_MANIFEST = ROOT / "translation" / "ziria_identity_rebuild.json"
Z3_RESULT = ROOT / "translation" / "ziria_section_link_result.json"
Z2_TRACK02 = ROOT / "module_relink" / "track02" / "Track02_data.identity.iso"
HOOK_PATH = ROOT / "translation" / "task3_field_getfnt_hook.bin"
HOOK_DESIGN = ROOT / "translation" / "task3_field_getfnt_hook_design.json"
FONT_PATH = ROOT / "font" / "Galmuri8x8.ttf"
BUILD_DIR = ROOT / "module_relink" / "z4_field_oneglyph_v3_builtin_slot"
LINKED_DIR = BUILD_DIR / "linked_modules"
OUTPUT_DIR = BUILD_DIR / "output"
REGISTRY_PATH = BUILD_DIR / "extension_registry.json"
TRACK02_OUT = BUILD_DIR / "Track02_data.z4.iso"
STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z4_field_oneglyph_v3_builtin_slot"
OUTPUT_BIN = OUTPUT_DIR / f"{STEM}.bin"
OUTPUT_CUE = OUTPUT_DIR / f"{STEM}.cue"
MANIFEST_PATH = ROOT / "translation" / "ziria_z4_field_oneglyph_v3_manifest.json"

EXPECTED_ORIGINAL_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_TRACK02 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"
EXPECTED_FONT = "97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05"
EXPECTED_HOOK = "677BC25A04CF7C3FFA035F5D20EF362987F9DED29847E4A04D388D65EB6362DB"
DATA_TRACK_OFFSET = 7_914_480
SECTOR = 2048


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def patch_bytes(image: bytearray, offset: int, expected: bytes, replacement: bytes, label: str) -> dict:
    if len(expected) != len(replacement):
        raise ValueError(f"length-changing module write rejected: {label}")
    actual = bytes(image[offset:offset + len(expected)])
    if actual != expected:
        raise ValueError(f"Expected Write mismatch for {label} at module offset 0x{offset:X}")
    image[offset:offset + len(replacement)] = replacement
    return {
        "id": label,
        "module_offset": f"0x{offset:X}",
        "length": len(replacement),
        "expected_hex": expected.hex().upper(),
        "replacement_hex": replacement.hex().upper(),
    }


def audit_changed_ranges(before: bytes, after: bytes) -> tuple[int, list[dict]]:
    if len(before) != len(after):
        raise ValueError("size changed during module link")
    count = 0
    ranges: list[list[int]] = []
    for index, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        count += 1
        if ranges and ranges[-1][1] == index:
            ranges[-1][1] += 1
        else:
            ranges.append([index, index + 1])
    return count, [
        {"start": f"0x{start:X}", "end_exclusive": f"0x{end:X}", "changed_bytes": end - start}
        for start, end in ranges
    ]


def copy_span(source, output, length: int) -> None:
    remaining = length
    while remaining:
        block = source.read(min(4 * 1024 * 1024, remaining))
        if not block:
            raise EOFError("short input during full BIN build")
        output.write(block)
        remaining -= len(block)


def main() -> None:
    if digest(ORIGINAL_BIN) != EXPECTED_ORIGINAL_BIN:
        raise ValueError("original BIN identity mismatch")
    if digest(Z2_TRACK02) != EXPECTED_TRACK02:
        raise ValueError("Z2 Track02 identity mismatch")
    if digest(FONT_PATH) != EXPECTED_FONT:
        raise ValueError("Galmuri8x8 identity mismatch")
    if digest(HOOK_PATH) != EXPECTED_HOOK:
        raise ValueError("field hook identity mismatch")

    z2 = load_json(Z2_MANIFEST)
    z3 = load_json(Z3_RESULT)
    design = load_json(HOOK_DESIGN)
    if z2["status"] != "PASS" or not z3["status"].startswith("PASS_"):
        raise ValueError("Z2/Z3 gate is not PASS")
    if design["hook"]["binary_sha256"] != EXPECTED_HOOK:
        raise ValueError("hook design and binary differ")
    semantic = {x["id"]: x for x in z2["semantic_modules"]}
    field_info = semantic["field.main_engine"]
    scene_info = semantic["scene.field_start"]

    registry = {
        "format": "ZIRIA-Z4-FIELD-LOCAL-REGISTRY",
        "version": 3,
        "status": "APPROVED_FOR_Z4_RUNTIME_PROBE",
        "family": "field",
        "approved_local_replacements": [
            {
                "id": "field-main-builtin-glyph-8754",
                "owner_module": "field.main_engine",
                "section": "existing_local_glyph_table",
                "module_offset": "0x5172",
                "runtime_address": "0x9172",
                "size": 32,
                "physical_bank": "0x82",
                "lifetime": "field.main_engine resident lifetime",
                "loader_registration": "unchanged existing LBA258/20 load",
                "allocation_proof": [
                    "original code at 966A..9697 explicitly handles 8754/8755",
                    "8754 selects the first 32-byte record at 9172",
                    "no original executable bytes or inferred padding are occupied",
                ],
            },
            {
                "id": "field-start-text-probe",
                "owner_module": "scene.field_start",
                "section": "text",
                "module_offset": f"0x{0x10B9F2 - scene_info['lba'] * SECTOR:X}",
                "size": 2,
                "lifetime": "scene.field_start only; reloaded after battle",
                "loader_registration": "unchanged overlay entry 2, LBA482/96",
            },
        ],
        "external_translation_modules": [],
        "prohibited": ["Work RAM execution", "automatic sidecar", "BIOS patch", "MPR change", "cross-family state"],
    }
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    legacy_hook = HOOK_PATH.read_bytes()
    if len(legacy_hook) != 77:
        raise ValueError("unexpected hook length")
    # Reuse only the Galmuri-derived expanded glyph from the former probe.  The
    # original renderer already dispatches 8754 to the 32-byte record at 9172.
    glyph = legacy_hook[45:]
    if len(glyph) != 32:
        raise ValueError("glyph length mismatch")

    field_source_path = ROOT / field_info["path"]
    field_before = field_source_path.read_bytes()
    field_after = bytearray(field_before)
    builtin_8754 = bytes.fromhex("00000F00060006000600060006000600060006000F0000000000000000000000")
    field_writes = [patch_bytes(field_after, 0x5172, builtin_8754, glyph, "field-main-builtin-glyph-8754")]
    field_output = LINKED_DIR / field_source_path.name
    field_output.write_bytes(field_after)
    field_changed, field_ranges = audit_changed_ranges(field_before, field_after)

    scene_source_path = ROOT / scene_info["path"]
    scene_before = scene_source_path.read_bytes()
    scene_after = bytearray(scene_before)
    scene_text_offset = 0x10B9F2 - scene_info["lba"] * SECTOR
    scene_writes = [
        patch_bytes(scene_after, scene_text_offset, bytes.fromhex("6F2D"), bytes.fromhex("8754"), "field-start-text-probe")
    ]
    scene_output = LINKED_DIR / scene_source_path.name
    scene_output.write_bytes(scene_after)
    scene_changed, scene_ranges = audit_changed_ranges(scene_before, scene_after)

    track_before = Z2_TRACK02.read_bytes()
    track_after = bytearray(track_before)
    for info, module_data in ((field_info, field_after), (scene_info, scene_after)):
        start = info["lba"] * SECTOR
        end = start + len(module_data)
        if bytes(track_after[start:end]) != (ROOT / info["path"]).read_bytes():
            raise ValueError(f"Track02 module identity mismatch before insertion: {info['id']}")
        track_after[start:end] = module_data
    TRACK02_OUT.write_bytes(track_after)
    track_changed, track_ranges = audit_changed_ranges(track_before, track_after)

    output_tmp = OUTPUT_BIN.with_suffix(".tmp")
    track_size = len(track_after)
    with ORIGINAL_BIN.open("rb") as source, output_tmp.open("wb") as output:
        copy_span(source, output, DATA_TRACK_OFFSET)
        output.write(track_after)
        source.seek(DATA_TRACK_OFFSET + track_size)
        copy_span(source, output, ORIGINAL_BIN.stat().st_size - DATA_TRACK_OFFSET - track_size)
    output_tmp.replace(OUTPUT_BIN)

    cue_text = ORIGINAL_CUE.read_text(encoding="ascii")
    if cue_text.count(ORIGINAL_BIN.name) != 1:
        raise ValueError("original CUE target is ambiguous")
    OUTPUT_CUE.write_text(cue_text.replace(ORIGINAL_BIN.name, OUTPUT_BIN.name), encoding="ascii", newline="")

    total_changed = field_changed + scene_changed
    if track_changed != total_changed or track_changed != 20:
        raise ValueError(f"unexpected changed-byte count: field={field_changed} scene={scene_changed} track={track_changed}")
    if OUTPUT_BIN.stat().st_size != ORIGINAL_BIN.stat().st_size:
        raise ValueError("full BIN size changed")
    if digest(ORIGINAL_BIN) != EXPECTED_ORIGINAL_BIN:
        raise ValueError("source BIN changed during build")

    manifest = {
        "format": "ZIRIA-Z4-FIELD-ONEGLYPH",
        "version": 3,
        "status": "STATIC_PASS_RUNTIME_PENDING",
        "source_bin_sha256": EXPECTED_ORIGINAL_BIN,
        "font": {"path": FONT_PATH.relative_to(ROOT).as_posix(), "sha256": EXPECTED_FONT, "glyph": "가"},
        "custom_code": "8754",
        "hook": {
            "type": "original field-local 8754/8755 dispatcher",
            "runtime_address": "0x966A",
            "code_bytes_changed": 0,
            "callsite_bytes_changed": 0,
            "glyph_runtime_address": "0x9172",
            "glyph_physical_bank": "0x82",
            "glyph_bytes": len(glyph),
            "fallback": "unchanged JSR $E060 original BIOS EX_GETFNT",
            "mpr_changes": 0,
            "work_ram_bytes": 0,
            "execution_policy": "no injected executable code; original renderer path only",
        },
        "registry": REGISTRY_PATH.relative_to(ROOT).as_posix(),
        "linked_modules": [
            {
                "id": "field.main_engine",
                "input": field_info["path"],
                "input_sha256": field_info["sha256"],
                "output": field_output.relative_to(ROOT).as_posix(),
                "output_sha256": digest(field_output),
                "changed_bytes": field_changed,
                "changed_ranges": field_ranges,
                "writes": field_writes,
            },
            {
                "id": "scene.field_start",
                "input": scene_info["path"],
                "input_sha256": scene_info["sha256"],
                "output": scene_output.relative_to(ROOT).as_posix(),
                "output_sha256": digest(scene_output),
                "changed_bytes": scene_changed,
                "changed_ranges": scene_ranges,
                "writes": scene_writes,
            },
        ],
        "track02": {
            "input": Z2_TRACK02.relative_to(ROOT).as_posix(),
            "input_sha256": EXPECTED_TRACK02,
            "output": TRACK02_OUT.relative_to(ROOT).as_posix(),
            "output_sha256": digest(TRACK02_OUT),
            "changed_bytes": track_changed,
            "changed_ranges": track_ranges,
            "sector_count_preserved": True,
            "loader_tables_changed": False,
        },
        "output": {
            "bin": OUTPUT_BIN.relative_to(ROOT).as_posix(),
            "bin_size": OUTPUT_BIN.stat().st_size,
            "bin_sha256": digest(OUTPUT_BIN),
            "cue": OUTPUT_CUE.relative_to(ROOT).as_posix(),
            "cue_sha256": digest(OUTPUT_CUE),
        },
        "diff_audit": {
            "actual_changed_bytes": track_changed,
            "changed_modules": ["field.main_engine", "scene.field_start"],
            "undeclared_changes": 0,
            "audio_changed_bytes": 0,
            "cue_track_layout_changed": False,
        },
        "runtime": {
            "status": "PENDING",
            "required_checks": [
                "first custom position renders 가",
                "later original Japanese glyphs use BIOS fallback",
                "Memo enter/return remains normal (regression gate for removing MPR6 execution)",
                "first battle attack and field return remain normal",
                "tower entry after battle remains normal",
            ],
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS field module changed bytes: {field_changed}")
    print(f"PASS field scene changed bytes: {scene_changed}")
    print(f"PASS total disc changed bytes: {track_changed}")
    print(OUTPUT_CUE)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
