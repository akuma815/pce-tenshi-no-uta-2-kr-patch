# -*- coding: utf-8 -*-
"""Build a broad, auditable text catalogue for Tenshi no Uta II.

The old extractor intentionally favours natural-looking dialogue.  This tool
keeps those verified rows, adds short/table/menu candidates from the original
ISO, and inventories external translation assets without pretending that
modern collection/launcher strings are present on the PC Engine disc.

Outputs are UTF-8 BOM CSV files so they open cleanly in Korean Excel.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ISO = ROOT / "extracted_bin" / "Track02_data.iso"
OLD_SHEET = ROOT / "translation" / "script_sheet.tsv"
ASSET_DIR = ROOT / "Translate_Original"
DEFAULT_OUT = ROOT / "translation" / "full_extraction"
SECTOR = 2048
SLOT_BASE = 162
SLOT_SIZE = 96
SLOT_COUNT = 55
BATCH_SIZE = 500

FIELDS = [
    "id", "category", "subcategory", "status", "source_kind",
    "source_name", "source_row", "iso_offset", "sector", "region",
    "raw_hex", "original", "translation", "controls", "duplicate_of",
    "evidence", "notes",
]


@dataclass
class Record:
    id: str
    category: str
    subcategory: str
    status: str
    source_kind: str
    source_name: str
    source_row: str
    iso_offset: str
    sector: str
    region: str
    raw_hex: str
    original: str
    translation: str
    controls: str
    duplicate_of: str
    evidence: str
    notes: str


def load_legacy_module():
    path = ROOT / "tools" / "extract_script.py"
    spec = importlib.util.spec_from_file_location("legacy_extract_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LEGACY = load_legacy_module()
KANA_VALUES = set(LEGACY.KANA.values())
CONTROL_RE = re.compile(r"\\[np]|\{[^{}]+\}")
ASSET_CONTROL_RE = re.compile(
    r"%(?:[0-9.]*[sdx]|[fF][0-9A-Fa-f.]*)|#[0-9A-Fa-f]+|\\[ebx]"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_text(value: str) -> str:
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\\n", "\n").replace("\\p", "\n")
    value = CONTROL_RE.sub("", value)
    value = ASSET_CONTROL_RE.sub("", value)
    value = value.replace("＿", "").replace("_", "")
    return re.sub(r"\s+", "", value).strip()


def contains_japanese(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if ch in KANA_VALUES or 0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x9FFF:
            return True
    return False


def visible_chars(text: str) -> list[str]:
    clean = CONTROL_RE.sub("", text)
    return [ch for ch in clean if not ch.isspace()]


def repetition_ratio(text: str) -> float:
    chars = visible_chars(text)
    if not chars:
        return 1.0
    return collections.Counter(chars).most_common(1)[0][1] / len(chars)


def area_for_sector(sec: int) -> tuple[str, str, str]:
    if sec < 2:
        return "disc_header", "header", "non_text_header"
    if sec < 18:
        return "boot", "boot", "boot_or_bios_text"
    if sec < SLOT_BASE:
        return "system", "system", "system_menu_battle"
    slot_end = SLOT_BASE + SLOT_SIZE * SLOT_COUNT
    if sec < slot_end:
        slot = (sec - SLOT_BASE) // SLOT_SIZE
        local = (sec - SLOT_BASE) % SLOT_SIZE
        if 32 <= local < 64:
            return f"slot{slot:02d}", "slot_graphics_window", "graphics_or_embedded_text"
        return f"slot{slot:02d}", "event", "event_dialogue_or_command"
    if sec < 5474:
        return "misc", "unknown", "unclassified_program_data"
    if sec < 5900:
        return "table", "data_table", "item_monster_name_candidate"
    if sec < 6044:
        return "battle", "battle", "battle_message_or_data"
    if sec < 6112:
        return "card", "card", "card_minigame_text"
    if sec < 6660:
        return "battle", "battle", "battle_message_or_data"
    if sec < 8700:
        return "visual_event", "visual_event", "visual_scene_or_overlay"
    if sec < 9178:
        return "late", "late_event", "late_event_or_program"
    return "tail", "tail", "post_program_or_non_text"


def controls_of(text: str) -> str:
    return " ".join(CONTROL_RE.findall(text))


def read_old_sheet() -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    with OLD_SHEET.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        if len(header) < 5:
            raise RuntimeError("script_sheet.tsv schema is not recognised")
        for row_no, row in enumerate(reader, 2):
            if len(row) < 5:
                continue
            try:
                off = int(row[0], 16)
            except ValueError:
                continue
            result[off] = {
                "row": str(row_no), "region": row[1], "duplicate": row[2],
                "original": row[3], "translation": row[4],
            }
    return result


def asset_category(name: str, table: str = "") -> tuple[str, str]:
    lower = name.lower()
    if "게임선택" in name:
        return "external_ui", "modern_collection_game_selector"
    if "ui" in lower:
        if table.startswith("DT_Game2"):
            return "external_ui", "modern_collection_game2_ui"
        if table.startswith("DT_Boot"):
            return "external_ui", "modern_collection_boot_notice"
        return "external_ui", "modern_collection_ui"
    if "크레딧" in name or "visualscene" in lower:
        return "visual_scene", "visual_scene_or_credits_asset"
    if "대사" in name or "3줄" in name:
        return "dialogue", "external_dialogue_asset"
    return "external", "unclassified_external_asset"


def load_external_assets() -> list[dict[str, str]]:
    """Load each logical source once, preferring CSV parts over matching XLSX."""
    rows: list[dict[str, str]] = []
    csv_files = sorted(ASSET_DIR.glob("*.csv"))
    for path in csv_files:
        if "줄별길이초과" in path.name:
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row_no, row in enumerate(reader, 2):
                jp = (row.get("jp") or row.get("Japanese") or "").strip()
                en = (row.get("en") or "").strip()
                ko = (row.get("ko") or row.get("Korean") or "").strip()
                table = (row.get("table") or "").strip()
                # The game-selector asset has no Japanese column.  Keep its
                # visible English source so it remains inventoried, but never
                # claim it is an ISO match without byte evidence.
                source_text = jp or en
                if not source_text:
                    continue
                category, subcategory = asset_category(path.name, table)
                rows.append({
                    "source_name": path.name,
                    "source_row": str(row_no),
                    "category": category,
                    "subcategory": subcategory,
                    "table": table,
                    "asset_offset": (row.get("offset") or row.get("index") or "").strip(),
                    "original": source_text,
                    "translation": ko,
                    "norm": normalize_text(source_text),
                })

    # If a workbook has no CSV counterpart, inventory it as well.
    csv_stems = {re.sub(r"_part_\d+$", "", p.stem) for p in csv_files}
    for path in sorted(ASSET_DIR.glob("*.xlsx")):
        if path.stem in csv_stems:
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            values = ws.iter_rows(values_only=True)
            header = [str(v or "").strip() for v in next(values, ())]
            index = {name.lower(): i for i, name in enumerate(header)}
            for row_no, values_row in enumerate(values, 2):
                def get(*names: str) -> str:
                    for name in names:
                        i = index.get(name.lower())
                        if i is not None and i < len(values_row):
                            return str(values_row[i] or "").strip()
                    return ""
                jp, en, ko = get("jp", "japanese"), get("en", "english"), get("ko", "korean")
                source_text = jp or en
                if not source_text:
                    continue
                table = get("table")
                category, subcategory = asset_category(path.name, table)
                rows.append({
                    "source_name": path.name, "source_row": str(row_no),
                    "category": category, "subcategory": subcategory,
                    "table": table, "asset_offset": get("offset", "index"),
                    "original": source_text, "translation": ko,
                    "norm": normalize_text(source_text),
                })
        wb.close()
    return rows


def scan_null_terminated(data: bytes):
    """Yield maximal custom-encoding runs that terminate with 00.

    Unlike the legacy scanner this deliberately allows one-character and
    kanji/katakana-only strings.  Classification later decides whether they
    are translation rows or forensic review candidates.
    """
    i, size = 0, len(data)
    while i < size:
        c = data[i]
        if (
            c in LEGACY.KANA or 0xA1 <= c <= 0xDF or LEGACY.is_lead(c)
            or c in {0x0B, 0x0C, 0x0D, 0x0E, 0x23, 0x25, 0x7E}
        ):
            end, text, chars, hira = LEGACY.decode_run(data, i, size)
            if chars >= 1 and end < size and data[end] == 0:
                yield i, end + 1, text, chars, hira
                i = end + 1
                continue
            if end > i:
                i = end
                continue
        i += 1


def scan_unterminated_sjis(data: bytes, occupied: list[tuple[int, int]]):
    """Yield bounded SJIS runs in known table/text zones for manual review."""
    occupied_iter = iter(sorted(occupied))
    current = next(occupied_iter, None)
    i, size = 0, len(data)
    while i < size:
        while current and i >= current[1]:
            current = next(occupied_iter, None)
        if current and current[0] <= i < current[1]:
            i = current[1]
            continue
        sec = i // SECTOR
        _, category, _ = area_for_sector(sec)
        if category not in {"system", "data_table", "battle", "card", "late_event"}:
            i += 1
            continue
        start = i
        out: list[str] = []
        while i + 1 < size and LEGACY.is_lead(data[i]) and LEGACY.is_trail(data[i + 1]):
            try:
                ch = data[i:i + 2].decode("shift_jis")
            except UnicodeDecodeError:
                break
            out.append(ch)
            i += 2
        text = "".join(out)
        if len(text) >= 2 and contains_japanese(text) and repetition_ratio(text) <= 0.60:
            yield start, i, text
        if i == start:
            i += 1


def classify_candidate(off: int, text: str, chars: int, hira: int) -> tuple[str, str, str, str]:
    region, category, subcategory = area_for_sector(off // SECTOR)
    visible = visible_chars(text)
    ratio = repetition_ratio(text)
    natural = False
    try:
        natural = bool(LEGACY.looks_dialogue(text, "late" if region in {"late", "visual_event"} else region))
    except Exception:
        natural = False

    if not contains_japanese(text) or ratio > (0.55 if len(visible) > 10 else 0.75):
        return region, category, subcategory, "forensic_candidate"
    if region == "tail" or category in {"header", "slot_graphics_window"}:
        return region, category, subcategory, "forensic_candidate"
    if natural:
        return region, category, subcategory, "probable_text"
    # Short and noun-heavy strings are exactly what the old dialogue filter
    # dropped, so keep them in the translation catalogue with review status.
    if category in {"system", "event", "data_table", "battle", "card", "late_event"}:
        return region, category, subcategory, "needs_review"
    if category == "visual_event" and chars >= 2:
        return region, category, subcategory, "needs_review"
    return region, category, subcategory, "forensic_candidate"


def raw_hex(data: bytes, start: int, end: int) -> str:
    return data[start:end].hex().upper()


def refine_asset_categories(records: list[Record]) -> None:
    """Apply names to structurally observed packed tables and their copies."""
    canonical_ranges = [
        (0x00499AB, 0x0049AD0, "menu_data", "character_and_magic_names"),
        (0x0049AD0, 0x0049BFA, "menu_data", "weapon_names"),
        (0x0049BFA, 0x0049CE3, "menu_data", "armour_names"),
        (0x0049CE3, 0x0049D37, "menu_data", "shield_names"),
        (0x0049D37, 0x0049D9B, "menu_data", "headgear_names"),
        (0x0049D9B, 0x0049F19, "menu_data", "accessory_and_key_item_names"),
        (0x0049F19, 0x004A1C0, "menu_data", "location_names"),
        (0x004A4E9, 0x004A5E0, "command", "battle_effect_commands"),
        (0x004A58F, 0x004A820, "command", "menu_and_shop_commands"),
        (0x00A3C3B, 0x00A3F20, "menu_data", "monster_names"),
        (0x00A7EF5, 0x00A7F20, "menu_data", "boss_names"),
    ]
    by_norm: dict[str, tuple[str, str]] = {}
    for rec in records:
        if rec.status == "verified":
            continue
        off = int(rec.iso_offset, 16)
        for lo, hi, category, subcategory in canonical_ranges:
            if lo <= off < hi:
                rec.category, rec.subcategory = category, subcategory
                by_norm.setdefault(normalize_text(rec.original), (category, subcategory))
                break

    # The same packed tables are copied into numerous field/overlay loads.
    for rec in records:
        if rec.status == "verified":
            continue
        mapped = by_norm.get(normalize_text(rec.original))
        if mapped:
            rec.category, rec.subcategory = mapped
        elif "\\n" in rec.original or "\\p" in rec.original or len(normalize_text(rec.original)) >= 18:
            rec.category, rec.subcategory = "dialogue", "asset_confirmed_event_text"
        elif rec.category == "event":
            rec.subcategory = "asset_confirmed_short_event_text"


def write_csv(path: Path, records, fields=FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(asdict(rec) if isinstance(rec, Record) else rec)


def write_batches(out_dir: Path, records: list[Record]):
    batch_dir = out_dir / "batches_500"
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True)
    for index, start in enumerate(range(0, len(records), BATCH_SIZE), 1):
        chunk = records[start:start + BATCH_SIZE]
        first = start + 1
        last = start + len(chunk)
        write_csv(batch_dir / f"text_{index:03d}_{first:05d}-{last:05d}.csv", chunk)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso", type=Path, default=DEFAULT_ISO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    iso = args.iso.resolve()
    out_dir = args.output.resolve()
    if not iso.is_file():
        raise FileNotFoundError(iso)

    data = iso.read_bytes()
    verified = read_old_sheet()
    verified_offsets = sorted(verified)
    assets = load_external_assets()
    asset_by_norm: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for asset in assets:
        if asset["norm"]:
            asset_by_norm[asset["norm"]].append(asset)

    physical: list[Record] = []
    forensic: list[Record] = []
    broad_rows: list[tuple[Record, bool, bool]] = []
    occupied: list[tuple[int, int]] = []
    found_offsets: set[int] = set()
    first_by_text: dict[str, str] = {}

    for off, end, text, chars, hira in scan_null_terminated(data):
        occupied.append((off, end))
        exact_old = verified.get(off)
        lo = bisect.bisect_left(verified_offsets, off)
        hi = bisect.bisect_left(verified_offsets, end)
        covered_old_offsets = verified_offsets[lo:hi]
        old = exact_old or (verified[covered_old_offsets[0]] if covered_old_offsets else None)
        region, category, subcategory, candidate_status = classify_candidate(off, text, chars, hira)
        norm = normalize_text(text)
        linked_assets = asset_by_norm.get(norm, [])
        if old:
            status = "verified" if exact_old else "verified_corrected_boundary"
            original = old["original"] if exact_old else text
            translation = old["translation"]
            evidence = "legacy_dialogue_extractor;iso_null_terminated"
            if not exact_old:
                evidence += ";control_led_boundary_correction"
            category = "dialogue" if category == "event" else category
            if linked_assets:
                evidence += ";external_text_match"
        else:
            status = candidate_status
            original = text
            translation = linked_assets[0]["translation"] if linked_assets else ""
            evidence = "iso_null_terminated_broad_scan"
            if linked_assets:
                evidence += ";external_text_match"
                if category in {"unknown", "visual_event"}:
                    category = linked_assets[0]["category"]
                    subcategory = linked_assets[0]["subcategory"]

        rec_id = f"iso:{off:07X}"
        duplicate = first_by_text.get(norm, "") if norm else ""
        if norm and not duplicate:
            first_by_text[norm] = rec_id
        notes = ""
        if linked_assets:
            names = sorted({a["source_name"] for a in linked_assets})
            notes = "asset_match=" + "|".join(names)
        rec = Record(
            id=rec_id, category=category, subcategory=subcategory,
            status=status, source_kind="iso", source_name=iso.name,
            source_row=old["row"] if old else "", iso_offset=f"0x{off:07X}",
            sector=str(off // SECTOR), region=region,
            raw_hex=raw_hex(data, off, end), original=original,
            translation=translation, controls=controls_of(original),
            duplicate_of=duplicate, evidence=evidence, notes=notes,
        )
        found_offsets.update(covered_old_offsets)
        broad_rows.append((rec, bool(old), bool(linked_assets)))

    # Exact matches against the existing human translation assets are strong
    # evidence, especially when several occur back-to-back as a packed name,
    # item, monster or menu table.  A one/two-character match in isolation can
    # happen by chance in graphics, so keep it reviewable rather than silently
    # promoting it.
    linked_rows = sorted(
        [rec for rec, is_old, linked in broad_rows if linked and not is_old],
        key=lambda r: int(r.iso_offset, 16),
    )
    clustered_ids: set[str] = set()
    cluster: list[Record] = []
    previous: int | None = None
    for rec in linked_rows + [None]:
        offset = int(rec.iso_offset, 16) if rec is not None else None
        if rec is not None and (previous is None or offset - previous <= 64):
            cluster.append(rec)
        else:
            if len(cluster) >= 3:
                clustered_ids.update(item.id for item in cluster)
            cluster = [rec] if rec is not None else []
        previous = offset

    for rec, is_old, linked in broad_rows:
        if is_old:
            physical.append(rec)
            continue
        norm_len = len(normalize_text(rec.original))
        if linked and rec.id in clustered_ids:
            rec.status = "verified_asset_cluster"
            rec.evidence += ";dense_asset_match_cluster"
            physical.append(rec)
        elif linked and norm_len >= 4:
            rec.status = "verified_asset_match"
            rec.evidence += ";long_exact_asset_match"
            physical.append(rec)
        elif linked:
            rec.status = "needs_review"
            rec.evidence += ";short_isolated_asset_match"
            physical.append(rec)
        else:
            rec.status = "forensic_candidate"
            forensic.append(rec)

    refine_asset_categories(physical)

    # Preserve any previously verified row that a changed broad decoder failed
    # to reproduce.  This should be zero and is treated as a coverage failure.
    missing_verified = sorted(set(verified) - found_offsets)
    for off in missing_verified:
        old = verified[off]
        # These rows start inside another maximal decodable run.  Preserve the
        # legacy evidence in the forensic queue instead of losing it or calling
        # it a newly verified physical boundary.
        forensic.append(Record(
            id=f"legacy-overlap:{off:07X}", category="dialogue",
            subcategory="legacy_nonmaximal_run", status="forensic_candidate",
            source_kind="legacy_extractor_overlap", source_name=OLD_SHEET.name,
            source_row=old["row"], iso_offset=f"0x{off:07X}",
            sector=str(off // SECTOR), region=old["region"], raw_hex="",
            original=old["original"], translation=old["translation"],
            controls=controls_of(old["original"]), duplicate_of=old["duplicate"],
            evidence="legacy_row_starts_inside_maximal_decode_run",
            notes="Requires runtime reference evidence before acceptance.",
        ))

    for off, end, text in scan_unterminated_sjis(data, occupied):
        region, category, subcategory = area_for_sector(off // SECTOR)
        forensic.append(Record(
            id=f"rawsjis:{off:07X}", category=category,
            subcategory=subcategory, status="forensic_candidate",
            source_kind="iso_unterminated_sjis", source_name=iso.name,
            source_row="", iso_offset=f"0x{off:07X}", sector=str(off // SECTOR),
            region=region, raw_hex=raw_hex(data, off, end), original=text,
            translation="", controls="", duplicate_of="",
            evidence="bounded_sjis_run_without_00_terminator",
            notes="Not translation-ready until a loader/table reference is confirmed.",
        ))

    # Duplicate references must only point to rows present in the translation
    # catalogue, never to a discarded forensic candidate.
    first_physical_by_text: dict[str, str] = {}
    for rec in sorted(physical, key=lambda r: int(r.iso_offset, 16)):
        norm = normalize_text(rec.original)
        rec.duplicate_of = first_physical_by_text.get(norm, "") if norm else ""
        if norm and not rec.duplicate_of:
            first_physical_by_text[norm] = rec.id

    physical_norms = {normalize_text(r.original) for r in physical if normalize_text(r.original)}
    physical_norm_list = sorted(physical_norms, key=len, reverse=True)
    external: list[Record] = []
    for index, asset in enumerate(assets, 1):
        matched = asset["norm"] in physical_norms
        collection_only = asset["subcategory"].startswith("modern_collection_")
        substring_match = False
        if not matched and not collection_only and len(asset["norm"]) >= 4:
            substring_match = any(
                asset["norm"] in norm or (len(norm) >= 4 and norm in asset["norm"])
                for norm in physical_norm_list
            )
        if collection_only:
            external_status = "collection_only_out_of_scope"
            external_evidence = "modern_collection_or_launcher_table"
        elif matched:
            external_status = "matched_to_iso_text"
            external_evidence = "normalised_text_match"
        elif substring_match:
            external_status = "matched_as_iso_substring"
            external_evidence = "normalised_substring_match"
        else:
            external_status = "external_unconfirmed"
            external_evidence = "asset_only"
        external.append(Record(
            id=f"asset:{index:05d}", category=asset["category"],
            subcategory=asset["subcategory"],
            status=external_status,
            source_kind="external_translation_asset",
            source_name=asset["source_name"], source_row=asset["source_row"],
            iso_offset="", sector="", region="external",
            raw_hex="", original=asset["original"],
            translation=asset["translation"], controls=controls_of(asset["original"]),
            duplicate_of="", evidence=external_evidence,
            notes=("table=" + asset["table"] + ";" if asset["table"] else "")
                  + ("asset_offset=" + asset["asset_offset"] if asset["asset_offset"] else ""),
        ))

    physical.sort(key=lambda r: int(r.iso_offset, 16))
    forensic.sort(key=lambda r: (int(r.iso_offset, 16), r.source_kind))
    write_csv(out_dir / "master_text.csv", physical)
    write_batches(out_dir, physical)
    write_csv(out_dir / "forensic_candidates.csv", forensic)
    write_csv(out_dir / "external_asset_inventory.csv", external)

    status_counts = collections.Counter(r.status for r in physical)
    category_counts = collections.Counter(r.category for r in physical)
    external_counts = collections.Counter(r.status for r in external)
    forensic_kind_counts = collections.Counter(r.source_kind for r in forensic)
    report = {
        "schema_version": 1,
        "iso": str(iso),
        "iso_size": len(data),
        "iso_sha256": sha256(iso),
        "batch_size": BATCH_SIZE,
        "physical_translation_rows": len(physical),
        "batch_count": (len(physical) + BATCH_SIZE - 1) // BATCH_SIZE,
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "forensic_candidate_rows": len(forensic),
        "forensic_source_kind_counts": dict(sorted(forensic_kind_counts.items())),
        "external_asset_rows": len(external),
        "external_status_counts": dict(sorted(external_counts.items())),
        "legacy_verified_rows": len(verified),
        "legacy_verified_missing_from_rescan": [f"0x{x:07X}" for x in missing_verified],
        "legacy_verified_overlap_rows_accounted_in_forensic_queue": len(missing_verified),
        "completion_gate": {
            "verified_rescan_gap_must_be_zero": not missing_verified,
            "needs_review_must_be_zero_for_no_omission_claim": status_counts.get("needs_review", 0) == 0,
            "forensic_candidates_must_be_classified": len(forensic) == 0,
            "external_unconfirmed_must_be_scoped": external_counts.get("external_unconfirmed", 0) == 0,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    inventory_fields = ["source", "kind", "rows", "scope", "notes"]
    inventory = [
        {"source": iso.name, "kind": "original_iso", "rows": len(physical),
         "scope": "physical translation catalogue",
         "notes": "verified plus broad null-terminated candidates"},
        {"source": "forensic_candidates.csv", "kind": "review_queue", "rows": len(forensic),
         "scope": "graphics/tail/unterminated SJIS candidates",
         "notes": "must be classified before claiming exhaustive coverage"},
        {"source": "external_asset_inventory.csv", "kind": "external_assets", "rows": len(external),
         "scope": "dialogue/UI/game selector/credits/visual scene assets",
         "notes": "modern collection-only strings remain external_unconfirmed"},
    ]
    write_csv(out_dir / "source_inventory.csv", inventory, inventory_fields)

    summary_fields = ["category", "status", "rows", "translated_rows", "empty_translation_rows"]
    summary = []
    for category, status in sorted({(r.category, r.status) for r in physical}):
        selected = [r for r in physical if r.category == category and r.status == status]
        translated = sum(bool(r.translation.strip()) for r in selected)
        summary.append({
            "category": category, "status": status, "rows": len(selected),
            "translated_rows": translated,
            "empty_translation_rows": len(selected) - translated,
        })
    write_csv(out_dir / "category_summary.csv", summary, summary_fields)

    readme = f"""# 전체 텍스트 추출 결과

- 원본 ISO SHA-256: `{report['iso_sha256']}`
- 번역용 물리 레코드: {len(physical):,}건
- 500건 단위 CSV: {report['batch_count']}개 (마지막 파일 제외 모두 500건)
- 원시 검수 후보: {len(forensic):,}건
- 외부 번역 자산 목록: {len(external):,}건

## 파일

- `batches_500/`: 실제 번역 작업용 CSV. ISO 오프셋 순서이며 500건 단위입니다.
- `master_text.csv`: 위 배치들을 합친 단일 원본입니다.
- `category_summary.csv`: 대사·메뉴 데이터·커맨드 등 범주/상태별 통계입니다.
- `forensic_candidates.csv`: 그래픽 오탐 가능성이나 로더 근거가 아직 없는 후보입니다.
- `external_asset_inventory.csv`: 기존 XLSX/CSV 자산과 ISO 일치 여부입니다.
- `coverage_report.json`: 재현성 및 완료 게이트입니다.

## 상태

- `verified`: 기존 런타임/대사 추출 경로로 확인된 문자열
- `verified_asset_cluster`: 기존 번역 자산과 일치하고 ISO에서 밀집 테이블을 이루는 문자열
- `verified_asset_match`: 4자 이상 외부 자산과 정확히 일치하는 ISO 문자열
- `needs_review`: 짧은 단독 일치라 사람이 용도를 확인해야 하는 문자열

`forensic_candidates.csv`와 `external_unconfirmed` 항목의 범위 판정이 끝나기 전에는
“누락 0건”으로 확정하지 않습니다.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    # A legacy overlap is reported as an open review item, not a tool failure;
    # every old row is still accounted for in one of the outputs.
    return 0


if __name__ == "__main__":
    sys.exit(main())
