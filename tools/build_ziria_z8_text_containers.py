#!/usr/bin/env python3
"""Build deterministic Z8 text containers without mutating the disc image.

The output is an indexed build input, not yet a runtime format.  It preserves
every physical master_text row, uses the package-local Z7 Hangul maps, and
records unresolved pointer/redirect questions instead of inventing defaults.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
ISO = ROOT / "extracted_bin" / "Track02_data.iso"
Z7 = ROOT / "translation" / "ziria_z7_glyph_packages_manifest.json"
OUTPUT_ROOT = ROOT / "module_relink" / "z8_text_containers"
CONTAINER_ROOT = OUTPUT_ROOT / "containers"
SEMANTIC_ROOT = OUTPUT_ROOT / "semantic_tables"
MANIFEST = ROOT / "translation" / "ziria_z8_text_containers_manifest.json"
ENTRY_INDEX = ROOT / "translation" / "ziria_z8_text_entry_index.csv"
SUMMARY_CSV = ROOT / "translation" / "ziria_z8_text_container_summary.csv"
CONTROL_SPEC = ROOT / "translation" / "ziria_z8_control_code_spec.json"
REPORT = ROOT / "docs" / "active" / "Z8_텍스트_컨테이너_v1.md"

EXPECTED_ISO_SHA256 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"
BANK = 8192
TOKEN_RE = re.compile(r"\\[np]|\{[^{}]+\}")
SLOT_RE = re.compile(r"slot(\d{2})")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

KANA = {}
for base, text in (
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
    for index, character in enumerate(text):
        KANA[character] = base + index

HALF2FULL = {
    character: 0xA1 + index
    for index, character in enumerate(
        "。「」、・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソ"
        "タチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"
    )
}
BYTE_TO_KANA = {value: key for key, value in KANA.items()}
BYTE_TO_HALF2FULL = {value: key for key, value in HALF2FULL.items()}
ENCODING_ALIASES = {
    # Keep the authored CSV text unchanged while selecting the game's native,
    # single-byte katakana middle-dot glyph for Korean U+00B7.
    "·": {"display": "・", "bytes": bytes((0xA5,)), "reason": "native middle-dot glyph"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def module_id(region: str) -> str:
    match = SLOT_RE.fullmatch(region)
    if match:
        return f"scene.slot{int(match.group(1)):02d}"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", region.strip() or "unclassified")
    return f"shared.{safe}"


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)


def token_sequence(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def strict_encode(text: str, glyph_map: dict[str, str]) -> bytes:
    output = bytearray()
    index = 0
    while index < len(text):
        if text.startswith("\\n", index):
            output.append(0x0D)
            index += 2
            continue
        if text.startswith("\\p", index):
            output.append(0x0C)
            index += 2
            continue
        matched = TOKEN_RE.match(text, index)
        if matched:
            token = matched.group(0)
            if token == "{0B}":
                output.append(0x0B)
            elif token == "{0E}":
                output.append(0x0E)
            elif token == "{~}":
                output.append(0x7E)
            elif len(token) == 4 and token[1] in "#%":
                argument = ord(token[2])
                if not 0x21 <= argument < 0x7F:
                    raise ValueError(f"control argument outside original grammar: {token}")
                output.extend((ord(token[1]), argument))
            else:
                raise ValueError(f"unsupported control token: {token}")
            index = matched.end()
            continue

        character = text[index]
        if character == "\x00":
            raise ValueError("embedded NUL in text")
        if character in ENCODING_ALIASES:
            output.extend(ENCODING_ALIASES[character]["bytes"])
        elif character in glyph_map:
            output.extend(bytes.fromhex(glyph_map[character]))
        elif "\uac00" <= character <= "\ud7a3":
            raise ValueError(f"unmapped Hangul U+{ord(character):04X}")
        elif character in KANA:
            output.append(KANA[character])
        elif character in HALF2FULL:
            output.append(HALF2FULL[character])
        else:
            try:
                encoded = character.encode("shift_jis")
            except UnicodeEncodeError as error:
                raise ValueError(f"unencodable character U+{ord(character):04X}") from error
            if b"\x00" in encoded:
                raise ValueError(f"character encodes to NUL: U+{ord(character):04X}")
            output.extend(encoded)
        index += 1
    return bytes(output)


def parse_original_body(raw: bytes) -> list[str]:
    if not raw or raw[-1] != 0:
        raise ValueError("raw record is not NUL-terminated")
    body = raw[:-1]
    index = 0
    tokens = []
    while index < len(body):
        code = body[index]
        if code == 0x0B:
            tokens.append("{0B}")
            index += 1
        elif code == 0x0C:
            tokens.append("\\p")
            index += 1
        elif code == 0x0D:
            tokens.append("\\n")
            index += 1
        elif code == 0x0E:
            tokens.append("{0E}")
            index += 1
        elif code == 0x7E:
            tokens.append("{~}")
            index += 1
        elif code in (0x23, 0x25):
            if index + 1 >= len(body) or not 0x21 <= body[index + 1] < 0x7F:
                raise ValueError(f"truncated control at body offset {index}")
            tokens.append("{" + chr(code) + chr(body[index + 1]) + "}")
            index += 2
        elif 0x28 <= code <= 0x7A or 0xA1 <= code <= 0xDF:
            index += 1
        elif (
            (0x81 <= code <= 0x9F or 0xE0 <= code <= 0xEA)
            and index + 1 < len(body)
            and (
                0x40 <= body[index + 1] <= 0x7E
                or 0x80 <= body[index + 1] <= 0xFC
            )
        ):
            index += 2
        else:
            raise ValueError(f"unparsed byte {code:02X} at body offset {index}")
    return tokens


def decode_original_body(raw: bytes) -> str:
    if not raw or raw[-1] != 0:
        raise ValueError("raw record is not NUL-terminated")
    body = raw[:-1]
    index = 0
    output = []
    while index < len(body):
        code = body[index]
        if code == 0x0B:
            output.append("{0B}")
            index += 1
        elif code == 0x0C:
            output.append("\\p")
            index += 1
        elif code == 0x0D:
            output.append("\\n")
            index += 1
        elif code == 0x0E:
            output.append("{0E}")
            index += 1
        elif code == 0x7E:
            output.append("{~}")
            index += 1
        elif code in (0x23, 0x25):
            if index + 1 >= len(body) or not 0x21 <= body[index + 1] < 0x7F:
                raise ValueError(f"truncated control at body offset {index}")
            output.append("{" + chr(code) + chr(body[index + 1]) + "}")
            index += 2
        elif code in BYTE_TO_KANA:
            output.append(BYTE_TO_KANA[code])
            index += 1
        elif code in BYTE_TO_HALF2FULL:
            output.append(BYTE_TO_HALF2FULL[code])
            index += 1
        elif (
            (0x81 <= code <= 0x9F or 0xE0 <= code <= 0xEA)
            and index + 1 < len(body)
            and (
                0x40 <= body[index + 1] <= 0x7E
                or 0x80 <= body[index + 1] <= 0xFC
            )
        ):
            output.append(body[index:index + 2].decode("shift_jis"))
            index += 2
        else:
            raise ValueError(f"unparsed byte {code:02X} at body offset {index}")
    return "".join(output)


def load_glyph_maps(z7: dict) -> dict[str, dict[str, str]]:
    result = {}
    for package in z7["packages"]:
        path = ROOT / package["paths"]["glyph_map"]
        if sha256(path) != package["sha256"]["glyph_map"]:
            raise ValueError(f"Z7 glyph map hash mismatch: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        result[package["package_id"]] = {
            row["character"]: row["code"] for row in rows
        }
    return result


def build_control_spec(families: list[str]) -> dict:
    family_profiles = {}
    for family in families:
        if family == "dialogue_event":
            pointer = "inline event bytecode stream; main $53/$54, auxiliary $55/$56, variable $57/$58"
            evidence = "field parser/fetch static analysis and runtime samples"
        else:
            pointer = "physical record known; complete reference/pointer catalogue not proven"
            evidence = "full extraction raw boundary plus renderer-family classification"
        family_profiles[family] = {
            "record_boundary": "00 terminator included in protected raw record",
            "pointer_model": pointer,
            "pointer_status": (
                "PARTIAL_INLINE_MODEL_REFERENCE_CATALOGUE_OPEN"
                if family == "dialogue_event"
                else "REFERENCE_CATALOGUE_OPEN"
            ),
            "continuation_model": "none inside extracted record",
            "redirect_model": "UNSELECTED; legacy 01/02 resident-hook protocol prohibited",
            "relocation_gate": "BLOCKED_UNTIL_LOADER_OWNED_REDIRECT_AND_REFERENCE_MODEL_PASS",
            "evidence": evidence,
        }
    return {
        "format": "ZIRIA-Z8-CONTROL-CODE-SPEC",
        "version": 1,
        "scope": "all 18,817 master_text physical records; semantic runtime proof remains renderer-scoped",
        "terminator": {
            "bytes": "00",
            "width": 1,
            "terminates": True,
            "policy": "regenerate exactly once at encoded string end",
            "evidence": "all protected raw records terminate with 00 and match Track02_data.iso",
        },
        "tokens": [
            {"token": "{0B}", "bytes": "0B", "width": 1, "meaning": "page-control variant; return-code 2 path", "policy": "forbidden_move_preserve"},
            {"token": "\\p", "bytes": "0C", "width": 1, "meaning": "page control", "policy": "preserve_order_and_count"},
            {"token": "\\n", "bytes": "0D", "width": 1, "meaning": "line break/window parameter update", "policy": "preserve_order_and_count"},
            {"token": "{0E}", "bytes": "0E", "width": 1, "meaning": "row counter increment", "policy": "forbidden_move_preserve"},
            {"token": "{#x}", "bytes": "23 xx", "width": 2, "meaning": "text colour/style state", "policy": "preserve_exact_argument_order"},
            {"token": "{%x}", "bytes": "25 xx", "width": 2, "meaning": "dynamic variable/string insertion", "policy": "preserve_exact_argument_order"},
            {"token": "{~}", "bytes": "7E", "width": 1, "meaning": "cursor advance", "policy": "preserve_order_and_count"},
        ],
        "translation_policy": {
            "current_gate": "exact token sequence equality",
            "movable_layout_tokens": [],
            "reason": "No renderer has yet approved automatic line/page token movement for the full corpus.",
        },
        "continuation_and_redirect": {
            "original_in_record_continuation": "none",
            "legacy_01_redirect_02_continuation": "REJECTED_WITH_RESIDENT_MEMORY_ARCHITECTURE",
            "current_ziria_protocol": "UNDEFINED_PENDING_LOADER_OWNED_Z8_POC",
        },
        "encoding_aliases": [
            {
                "source": character,
                "source_codepoint": f"U+{ord(character):04X}",
                "display_equivalent": details["display"],
                "encoded_bytes": details["bytes"].hex().upper(),
                "reason": details["reason"],
                "master_text_mutated": False,
            }
            for character, details in ENCODING_ALIASES.items()
        ],
        "family_profiles": family_profiles,
    }


def main() -> None:
    for path in (MASTER, ISO, Z7):
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha256(ISO) != EXPECTED_ISO_SHA256:
        raise ValueError("Track02_data.iso identity mismatch")
    z7 = json.loads(Z7.read_text(encoding="utf-8"))
    if z7["format"] != "ZIRIA-Z7-MODULE-GLYPH-PACKAGES":
        raise ValueError("Z7 manifest format mismatch")
    if sha256(MASTER) != z7["inputs"]["master_text"]["sha256"]:
        raise ValueError("master_text differs from Z7 baseline")
    family_map = z7["classification"]["renderer_axis"]
    glyph_maps = load_glyph_maps(z7)

    with MASTER.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    iso = ISO.read_bytes()
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate stable IDs")

    grouped: dict[str, list[dict]] = defaultdict(list)
    token_counts = Counter()
    physical_duplicate_targets = {row["id"] for row in rows}
    previous_offset = -1
    for ordinal, row in enumerate(rows):
        offset = int(row["iso_offset"], 16)
        raw = bytes.fromhex(row["raw_hex"])
        if offset < previous_offset:
            raise ValueError(f"master order regression: {row['id']}")
        previous_offset = offset
        if iso[offset:offset + len(raw)] != raw:
            raise ValueError(f"protected raw mismatch: {row['id']}")
        raw_tokens = parse_original_body(raw)
        original_tokens = token_sequence(row["original"])
        translation_tokens = token_sequence(row["translation"])
        if raw_tokens != original_tokens:
            raise ValueError(f"raw/original token mismatch: {row['id']}")
        if original_tokens != translation_tokens:
            raise ValueError(f"original/translation token mismatch: {row['id']}")
        token_counts.update(raw_tokens)
        if row["duplicate_of"] and row["duplicate_of"] not in physical_duplicate_targets:
            raise ValueError(f"invalid duplicate target: {row['id']}")

        family = family_map[row["category"]]
        storage = module_id(row["region"])
        package_id = f"{storage}.{family}"
        glyph_map = glyph_maps.get(package_id, {})
        if decode_original_body(raw) != row["original"]:
            raise ValueError(f"protected original decode mismatch: {row['id']}")
        translated = strict_encode(row["translation"], glyph_map) + b"\x00"
        grouped[package_id].append(
            {
                "_ordinal": ordinal,
                "_translated": translated,
                "id": row["id"],
                "category": row["category"],
                "subcategory": row["subcategory"],
                "status": row["status"],
                "iso_offset": row["iso_offset"].upper(),
                "sector": row["sector"],
                "region": row["region"],
                "storage_module": storage,
                "family": family,
                "package_id": package_id,
                "raw_hex": row["raw_hex"].upper(),
                "raw_length": len(raw),
                "original": row["original"],
                "translation": row["translation"],
                "controls": row["controls"],
                "duplicate_of": row["duplicate_of"],
                "encoded_length": len(translated),
                "encoded_sha256": bytes_sha256(translated),
                "encoded_hex": translated.hex().upper(),
                "length_delta": len(translated) - len(raw),
                "candidate_fixed_length": "yes" if len(translated) <= len(raw) else "no",
                "selected_reinsertion_mode": "UNRESOLVED_Z8_REDIRECT_REQUIRED",
                "terminator_policy": "NUL_00_REGENERATE_ONCE",
                "token_policy": "EXACT_SEQUENCE_PRESERVE",
                "pointer_status": (
                    "PARTIAL_INLINE_MODEL_REFERENCE_CATALOGUE_OPEN"
                    if family == "dialogue_event"
                    else "REFERENCE_CATALOGUE_OPEN"
                ),
                "release_eligibility": (
                    "BLOCKED_NEEDS_REVIEW"
                    if row["status"] == "needs_review"
                    else "STRUCTURE_PASS_TRANSLATION_POLICY_PENDING"
                ),
                "same_as_original": "yes" if row["translation"] == row["original"] else "no",
                "translation_has_japanese": "yes" if JAPANESE_RE.search(row["translation"]) else "no",
                "encoding_aliases": ";".join(
                    f"U+{ord(character):04X}->"
                    f"{ENCODING_ALIASES[character]['bytes'].hex().upper()}:"
                    f"{row['translation'].count(character)}"
                    for character in ENCODING_ALIASES
                    if character in row["translation"]
                ),
            }
        )

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    CONTAINER_ROOT.mkdir(parents=True)
    all_entry_rows = []
    summaries = []
    container_manifests = []
    cross_bank_errors = []

    for package_id in sorted(grouped):
        entries = grouped[package_id]
        directory = CONTAINER_ROOT / safe_name(package_id)
        directory.mkdir(parents=True)
        pool = bytearray()
        locations: dict[bytes, int] = {}
        padding_bytes = 0
        for entry in entries:
            encoded = entry["_translated"]
            if len(encoded) > BANK:
                raise ValueError(f"single string exceeds 8 KiB: {entry['id']}")
            already_stored = encoded in locations
            if encoded not in locations:
                inside = len(pool) % BANK
                if inside + len(encoded) > BANK:
                    padding = BANK - inside
                    pool.extend(b"\xFF" * padding)
                    padding_bytes += padding
                locations[encoded] = len(pool)
                pool.extend(encoded)
            offset = locations[encoded]
            entry["container_offset"] = f"0x{offset:06X}"
            entry["container_end_exclusive"] = f"0x{offset + len(encoded):06X}"
            entry["deduplicated"] = "yes" if already_stored else "no"
            if offset // BANK != (offset + len(encoded) - 1) // BANK:
                cross_bank_errors.append(entry["id"])

        clean_entries = []
        for entry in entries:
            clean_entries.append({key: value for key, value in entry.items() if not key.startswith("_")})
        entry_path = directory / "entries.csv"
        pool_path = directory / "strings.bin"
        profile_path = directory / "container_profile.json"
        pool_path.write_bytes(pool)
        write_csv(entry_path, list(clean_entries[0].keys()), clean_entries)
        family = entries[0]["family"]
        profile = {
            "format": "ZIRIA-Z8-TEXT-CONTAINER-PROFILE",
            "version": 1,
            "package_id": package_id,
            "storage_module": entries[0]["storage_module"],
            "family": family,
            "runtime_status": "NOT_LINKED_ANALYSIS_CONTAINER",
            "string_terminator": "00",
            "alignment": 1,
            "bank_bytes": BANK,
            "bank_crossing": "prohibited by generated offsets",
            "inter_string_padding": "FF outside indexed string ranges; never consumer-visible",
            "index_format": "entries.csv only; runtime pointer representation unresolved",
            "deduplication": "exact final encoded byte identity within this package",
            "control_spec": str(CONTROL_SPEC.relative_to(ROOT)).replace("\\", "/"),
            "glyph_package": (
                f"module_relink/z7_glyph_packages/packages/{safe_name(package_id)}"
                if package_id in glyph_maps
                else None
            ),
            "relocation_gate": "BLOCKED_UNTIL_LOADER_OWNED_REDIRECT_AND_REFERENCE_MODEL_PASS",
        }
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        unique_strings = len(locations)
        summary = {
            "package_id": package_id,
            "storage_module": entries[0]["storage_module"],
            "family": family,
            "row_count": len(entries),
            "unique_encoded_strings": unique_strings,
            "deduplicated_rows": len(entries) - unique_strings,
            "container_bytes": len(pool),
            "padding_bytes": padding_bytes,
            "original_bytes": sum(entry["raw_length"] for entry in entries),
            "translated_bytes_before_dedup": sum(entry["encoded_length"] for entry in entries),
            "fixed_length_candidates": sum(entry["candidate_fixed_length"] == "yes" for entry in entries),
            "relocation_required_by_length": sum(entry["candidate_fixed_length"] == "no" for entry in entries),
            "needs_review_rows": sum(entry["status"] == "needs_review" for entry in entries),
            "same_as_original_rows": sum(entry["same_as_original"] == "yes" for entry in entries),
            "japanese_translation_rows": sum(entry["translation_has_japanese"] == "yes" for entry in entries),
        }
        summaries.append(summary)
        container_manifests.append(
            {
                **summary,
                "paths": {
                    "entries": str(entry_path.relative_to(ROOT)).replace("\\", "/"),
                    "strings": str(pool_path.relative_to(ROOT)).replace("\\", "/"),
                    "profile": str(profile_path.relative_to(ROOT)).replace("\\", "/"),
                },
                "sha256": {
                    "entries": sha256(entry_path),
                    "strings": sha256(pool_path),
                    "profile": sha256(profile_path),
                },
            }
        )
        all_entry_rows.extend(clean_entries)

    all_entry_rows.sort(key=lambda row: int(row["iso_offset"], 16))
    write_csv(ENTRY_INDEX, list(all_entry_rows[0].keys()), all_entry_rows)
    write_csv(SUMMARY_CSV, list(summaries[0].keys()), summaries)
    semantic_tables = []
    semantic_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in all_entry_rows:
        semantic_groups[(entry["category"], entry["subcategory"])].append(entry)
    for (category, subcategory), semantic_rows in sorted(semantic_groups.items()):
        semantic_path = (
            SEMANTIC_ROOT
            / safe_name(category)
            / f"{safe_name(subcategory)}.csv"
        )
        write_csv(semantic_path, list(semantic_rows[0].keys()), semantic_rows)
        semantic_tables.append(
            {
                "category": category,
                "subcategory": subcategory,
                "rows": len(semantic_rows),
                "path": str(semantic_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(semantic_path),
            }
        )

    families = sorted({row["family"] for row in all_entry_rows})
    control_spec = build_control_spec(families)
    control_spec["audit"] = {
        "rows": len(rows),
        "raw_parse_errors": 0,
        "raw_original_token_mismatches": 0,
        "original_translation_token_mismatches": 0,
        "token_counts": dict(sorted(token_counts.items())),
        "cross_bank_strings": len(cross_bank_errors),
    }
    CONTROL_SPEC.write_text(
        json.dumps(control_spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "format": "ZIRIA-Z8-TEXT-CONTAINERS",
        "version": 1,
        "task": "Z8-v1",
        "status": "STRUCTURE_PASS_RELOCATION_BLOCKED",
        "scope": "all master_text rows; analysis containers only; no CUE/BIN mutation",
        "inputs": {
            "master_text": {"path": str(MASTER.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(MASTER)},
            "track02_iso": {"path": str(ISO.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(ISO)},
            "z7_manifest": {"path": str(Z7.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(Z7)},
        },
        "population": {
            "physical_rows": len(rows),
            "container_count": len(container_manifests),
            "stable_ids_unique": len({row["id"] for row in rows}) == len(rows),
            "protected_raw_matches": len(rows),
            "nul_terminated_rows": len(rows),
            "duplicate_reference_rows": sum(bool(row["duplicate_of"]) for row in rows),
        },
        "encoding_audit": {
            "protected_original_decode_rows": len(rows),
            "translation_encoded_rows": len(rows),
            "unmapped_characters": 0,
            "token_sequence_mismatches": 0,
            "cross_bank_strings": len(cross_bank_errors),
            "encoding_alias_rows": sum(bool(row["encoding_aliases"]) for row in all_entry_rows),
            "encoding_alias_occurrences": sum(
                row["translation"].count(character)
                for row in all_entry_rows
                for character in ENCODING_ALIASES
            ),
        },
        "size_summary": {
            "original_bytes": sum(item["original_bytes"] for item in summaries),
            "translated_bytes_before_dedup": sum(item["translated_bytes_before_dedup"] for item in summaries),
            "generated_container_bytes": sum(item["container_bytes"] for item in summaries),
            "padding_bytes": sum(item["padding_bytes"] for item in summaries),
            "fixed_length_candidates": sum(item["fixed_length_candidates"] for item in summaries),
            "relocation_required_by_length": sum(item["relocation_required_by_length"] for item in summaries),
            "largest_container_bytes": max(item["container_bytes"] for item in summaries),
        },
        "release_blockers": {
            "needs_review_rows": sum(item["needs_review_rows"] for item in summaries),
            "same_as_original_rows": sum(item["same_as_original_rows"] for item in summaries),
            "translation_rows_with_japanese": sum(item["japanese_translation_rows"] for item in summaries),
            "reference_catalogue": "OPEN_BY_RENDERER_FAMILY",
            "redirect_protocol": "UNDEFINED_FOR_ZIRIA_LOADER_OWNED_ARCHITECTURE",
            "runtime_pointer_format": "UNDEFINED",
        },
        "decisions": {
            "terminator": "00 confirmed and regenerated exactly once",
            "tokens": "exact original/translation token sequence required",
            "continuation": "no in-record continuation; legacy 01/02 protocol rejected",
            "deduplication": "exact encoded bytes only, package-local",
            "bank_crossing": "prohibited",
            "runtime_link": "not attempted",
        },
        "outputs": {
            "container_root": str(CONTAINER_ROOT.relative_to(ROOT)).replace("\\", "/"),
            "entry_index": str(ENTRY_INDEX.relative_to(ROOT)).replace("\\", "/"),
            "summary": str(SUMMARY_CSV.relative_to(ROOT)).replace("\\", "/"),
            "control_spec": str(CONTROL_SPEC.relative_to(ROOT)).replace("\\", "/"),
            "semantic_table_root": str(SEMANTIC_ROOT.relative_to(ROOT)).replace("\\", "/"),
            "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        },
        "semantic_tables": semantic_tables,
        "containers": container_manifests,
        "next_gate": (
            "Choose one renderer family and prove every source reference plus a loader-owned "
            "redirect/index representation before linking any container into a module."
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    largest = sorted(summaries, key=lambda item: (-item["container_bytes"], item["package_id"]))[:15]
    report = [
        "# Z8 텍스트 컨테이너 v1",
        "",
        "Z7의 module/family 분류와 로컬 글리프 맵을 사용해 전체 번역을 엄격하게 "
        "인코딩한 분석 컨테이너다. 아직 게임이 소비하는 runtime pointer/index 형식은 아니다.",
        "",
        "## 결과",
        "",
        f"- 물리 레코드: **{len(rows)}개**",
        f"- 텍스트 컨테이너: **{len(container_manifests)}개**",
        f"- 원본 raw/ISO 일치 및 보호 원문 디코딩: **{len(rows)}개 전부 PASS**",
        "- 원문/번역 제어 토큰 순서 불일치: **0건**",
        "- 미매핑 문자: **0건**",
        f"- 명시적 중점 인코딩 별칭: **{manifest['encoding_audit']['encoding_alias_rows']}행 / "
        f"{manifest['encoding_audit']['encoding_alias_occurrences']}회** (`U+00B7` → `A5`, 원본 CSV 불변)",
        f"- category/subcategory 의미 테이블: **{len(semantic_tables)}개**",
        f"- 고정 길이 후보: **{manifest['size_summary']['fixed_length_candidates']}개**",
        f"- 길이만으로 재배치가 필요한 항목: **{manifest['size_summary']['relocation_required_by_length']}개**",
        f"- 컨테이너 총량: **{manifest['size_summary']['generated_container_bytes']}바이트**",
        f"- 최대 컨테이너: **{manifest['size_summary']['largest_container_bytes']}바이트**",
        "",
        "## 확정한 경계",
        "",
        "- 모든 원본 엔트리는 `00`으로 종료하며 container 인코더도 끝에 정확히 한 번 생성한다.",
        "- `0B`, `0C`, `0D`, `0E`, `#x`, `%x`, `7E`는 원본과 번역에서 바이트 인자와 "
        "순서를 그대로 보존한다.",
        "- 패키지 안에서 최종 인코딩 바이트가 완전히 같은 문자열만 dedup한다.",
        "- 어떤 문자열도 8 KiB 경계를 넘지 않도록 배치한다.",
        "- 과거 `01/02` redirect/continuation은 폐기 설계로 분류하며 재사용하지 않는다.",
        "",
        "## 아직 확정하지 않은 경계",
        "",
        "- renderer별 전체 참조/포인터 카탈로그",
        "- loader-owned redirect 또는 index의 실제 바이트 형식",
        "- 컨테이너를 읽을 RAM 주소, MPR 상태와 수명",
        "- 고정 길이 후보를 제자리 치환할 수 있는 renderer별 패딩 규칙",
        "",
        "따라서 v1 상태는 `STRUCTURE_PASS_RELOCATION_BLOCKED`다. 다음 게이트에서는 "
        "한 renderer family만 선택해 참조 분모와 loader-owned redirect를 먼저 증명한다.",
        "",
        "## 큰 컨테이너 상위 15개",
        "",
        "| Container | 행 | 고유 문자열 | bytes | 길이 초과 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in largest:
        report.append(
            f"| `{item['package_id']}` | {item['row_count']} | "
            f"{item['unique_encoded_strings']} | {item['container_bytes']} | "
            f"{item['relocation_required_by_length']} |"
        )
    report.extend(
        [
            "",
            "## 산출물",
            "",
            f"- `{MANIFEST.relative_to(ROOT).as_posix()}`",
            f"- `{ENTRY_INDEX.relative_to(ROOT).as_posix()}`",
            f"- `{SUMMARY_CSV.relative_to(ROOT).as_posix()}`",
            f"- `{CONTROL_SPEC.relative_to(ROOT).as_posix()}`",
            f"- `{CONTAINER_ROOT.relative_to(ROOT).as_posix()}`",
            f"- `{SEMANTIC_ROOT.relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST.relative_to(ROOT)),
                "status": manifest["status"],
                "rows": len(rows),
                "containers": len(container_manifests),
                "fixed_length_candidates": manifest["size_summary"]["fixed_length_candidates"],
                "relocation_required_by_length": manifest["size_summary"]["relocation_required_by_length"],
                "generated_container_bytes": manifest["size_summary"]["generated_container_bytes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
