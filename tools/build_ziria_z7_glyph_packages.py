#!/usr/bin/env python3
"""Build deterministic Z7 module-local Hangul glyph packages.

This tool is analysis/build-input only.  It never opens or writes a CUE/BIN.
The translation SSOT is classified along two independent axes:

* storage module: the extraction ``region`` (slotNN or a shared region)
* renderer family: a conservative category-derived consumer family

Each non-empty module/family intersection receives its own local code map and
Galmuri8x8 glyph pools.  This deliberately duplicates glyphs on disk so no
package depends on persistent cross-family RAM.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "translation" / "full_extraction" / "master_text.csv"
FONT_POLICY = ROOT / "translation" / "font_build_policy.json"
FONT = ROOT / "font" / "Galmuri8x8.ttf"
SLOT_TOPOLOGY = ROOT / "translation" / "slot_topology.json"
OVERLAY_TOPOLOGY = ROOT / "translation" / "overlay_topology.json"
OUTPUT_ROOT = ROOT / "module_relink" / "z7_glyph_packages"
PACKAGE_ROOT = OUTPUT_ROOT / "packages"
MANIFEST = ROOT / "translation" / "ziria_z7_glyph_packages_manifest.json"
PACKAGE_SUMMARY = ROOT / "translation" / "ziria_z7_module_glyph_packages.csv"
GLYPH_MEMBERSHIP = ROOT / "translation" / "ziria_z7_glyph_membership.csv"
REPORT = ROOT / "docs" / "active" / "Z7_모듈별_글리프_패키지.md"

EXPECTED_FONT_SHA256 = "97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05"
CONTROL_RE = re.compile(r"\{[^{}]*\}|\\[np]")
SLOT_RE = re.compile(r"slot(\d{2})")
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

FAMILY_BY_CATEGORY = {
    "dialogue": "dialogue_event",
    "event": "dialogue_event",
    "late_event": "dialogue_event",
    "menu_data": "menu_memo_system",
    "command": "menu_memo_system",
    "system": "menu_memo_system",
    "data_table": "menu_memo_system",
    "unknown": "menu_memo_system",
    "battle": "battle",
    "visual_event": "visual_event_portrait",
    "visual_scene": "visual_event_portrait",
    "slot_graphics_window": "visual_event_portrait",
    "card": "card",
    "boot": "boot_opening",
}
CORE_FAMILIES = (
    "dialogue_event",
    "menu_memo_system",
    "battle",
    "visual_event_portrait",
)
GLYPH_BYTES_EXPANDED = 32
GLYPH_BYTES_PACKED = 18
MAP_BYTES_PER_GLYPH = 4
METRIC_BYTES_PER_GLYPH = 2
PACKAGE_HEADER_BYTES = 64


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def custom_codes() -> list[bytes]:
    trails = list(range(0x40, 0x7F)) + list(range(0x80, 0xFD))
    return [bytes((lead, trail)) for lead in range(0xEB, 0xF0) for trail in trails]


def render_glyph(font: ImageFont.FreeTypeFont, character: str) -> tuple[bytes, dict]:
    temporary = Image.new("1", (16, 16), 0)
    ImageDraw.Draw(temporary).text((0, 0), character, font=font, fill=1)
    bbox = temporary.getbbox()
    if bbox is None:
        raise ValueError(f"Galmuri8x8 has no visible glyph for U+{ord(character):04X}")
    ink = temporary.crop(bbox)
    if ink.width > 12 or ink.height > 12:
        raise ValueError(
            f"glyph exceeds 12x12 cell: U+{ord(character):04X} {ink.width}x{ink.height}"
        )
    x = (12 - ink.width) // 2
    y = (12 - ink.height) // 2
    canvas = Image.new("1", (16, 16), 0)
    canvas.paste(ink, (x, y))
    expanded = bytearray(32)
    for row in range(16):
        for column in range(16):
            if canvas.getpixel((column, row)):
                expanded[row * 2 + column // 8] |= 1 << (7 - column % 8)
    return bytes(expanded), {
        "ink_width": ink.width,
        "ink_height": ink.height,
        "paste_x": x,
        "paste_y": y,
        "advance": 12,
    }


def pack_expanded_glyph(expanded: bytes) -> bytes:
    if len(expanded) != 32:
        raise ValueError("expanded glyph must be 32 bytes")
    rows = []
    for y in range(12):
        word = (expanded[y * 2] << 8) | expanded[y * 2 + 1]
        if word & 0x000F:
            raise ValueError("glyph uses pixels outside the packed 12-column cell")
        rows.append(word >> 4)
    packed = bytearray()
    for y in range(0, 12, 2):
        row0, row1 = rows[y], rows[y + 1]
        packed.extend(
            (row0 >> 4, ((row0 & 0x0F) << 4) | (row1 >> 8), row1 & 0xFF)
        )
    return bytes(packed)


def expand_packed_glyph(packed: bytes) -> bytes:
    if len(packed) != 18:
        raise ValueError("packed glyph must be 18 bytes")
    expanded = bytearray()
    for index in range(0, 18, 3):
        byte0, byte1, byte2 = packed[index:index + 3]
        expanded.extend(
            (
                byte0,
                byte1 & 0xF0,
                ((byte1 & 0x0F) << 4) | (byte2 >> 4),
                (byte2 & 0x0F) << 4,
            )
        )
    expanded.extend(bytes(8))
    return bytes(expanded)


def storage_module(region: str) -> tuple[str, int | None]:
    match = SLOT_RE.fullmatch(region)
    if match:
        slot = int(match.group(1))
        return f"scene.slot{slot:02d}", slot
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", region.strip() or "unclassified")
    return f"shared.{safe}", None


def package_dir_name(package_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", package_id)


def main() -> None:
    for path in (MASTER, FONT_POLICY, FONT, SLOT_TOPOLOGY, OVERLAY_TOPOLOGY):
        if not path.is_file():
            raise FileNotFoundError(path)

    policy = json.loads(FONT_POLICY.read_text(encoding="utf-8"))
    if policy.get("status") != "ACTIVE":
        raise ValueError("font build policy is not ACTIVE")
    if policy["font"]["path"] != "font/Galmuri8x8.ttf":
        raise ValueError("font policy path mismatch")
    if policy["font"]["sha256"] != EXPECTED_FONT_SHA256:
        raise ValueError("font policy expected hash mismatch")
    if sha256(FONT) != EXPECTED_FONT_SHA256:
        raise ValueError("Galmuri8x8 identity mismatch")

    with MASTER.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("master_text.csv is empty")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate master_text IDs")

    unknown_categories = sorted({row["category"] for row in rows} - FAMILY_BY_CATEGORY.keys())
    if unknown_categories:
        raise ValueError(f"unclassified categories: {unknown_categories}")

    package_rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    family_rows: dict[str, list[dict]] = defaultdict(list)
    row_assignments = []
    for row in rows:
        family = FAMILY_BY_CATEGORY[row["category"]]
        module_id, slot = storage_module(row["region"])
        text = row["translation"]
        glyphs = sorted(set(HANGUL_RE.findall(CONTROL_RE.sub("", text))))
        assignment = {
            "id": row["id"],
            "category": row["category"],
            "family": family,
            "module_id": module_id,
            "slot": slot,
            "glyphs": glyphs,
        }
        row_assignments.append(assignment)
        family_rows[family].append(assignment)
        if glyphs:
            package_rows[(module_id, family)].append(assignment)

    family_sets = {
        family: set().union(*(set(row["glyphs"]) for row in family_assignments))
        if family_assignments else set()
        for family, family_assignments in family_rows.items()
    }
    missing_core_families = [family for family in CORE_FAMILIES if not family_sets.get(family)]
    if missing_core_families:
        raise ValueError(f"core families have no Hangul: {missing_core_families}")
    strict_core = set.intersection(*(family_sets[family] for family in CORE_FAMILIES))
    all_nonempty_sets = [glyphs for glyphs in family_sets.values() if glyphs]
    all_family_core = set.intersection(*all_nonempty_sets)

    global_counter = Counter(
        glyph
        for row in rows
        for glyph in HANGUL_RE.findall(CONTROL_RE.sub("", row["translation"]))
    )
    global_glyphs = sorted(global_counter)

    font = ImageFont.truetype(str(FONT), policy["render_profile"]["loader_size_argument"])
    rendered: dict[str, bytes] = {}
    packed: dict[str, bytes] = {}
    metrics: dict[str, dict] = {}
    for glyph in global_glyphs:
        expanded, metric = render_glyph(font, glyph)
        packed_glyph = pack_expanded_glyph(expanded)
        if expand_packed_glyph(packed_glyph) != expanded:
            raise ValueError(f"packed round-trip mismatch: U+{ord(glyph):04X}")
        rendered[glyph] = expanded
        packed[glyph] = packed_glyph
        metrics[glyph] = metric

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    PACKAGE_ROOT.mkdir(parents=True)
    codes = custom_codes()
    package_summaries = []
    package_manifests = []
    glyph_package_counts = Counter()

    for module_id, family in sorted(package_rows):
        assignments = package_rows[(module_id, family)]
        glyphs = sorted(set().union(*(set(row["glyphs"]) for row in assignments)))
        if len(glyphs) > len(codes):
            raise ValueError(
                f"{module_id}/{family} needs {len(glyphs)} codes; capacity is {len(codes)}"
            )
        package_id = f"{module_id}.{family}"
        directory = PACKAGE_ROOT / package_dir_name(package_id)
        directory.mkdir(parents=True)
        map_rows = []
        expanded_pool = bytearray()
        packed_pool = bytearray()
        for index, glyph in enumerate(glyphs):
            code = codes[index]
            metric = metrics[glyph]
            expanded_pool.extend(rendered[glyph])
            packed_pool.extend(packed[glyph])
            glyph_package_counts[glyph] += 1
            map_rows.append(
                {
                    "index": index,
                    "character": glyph,
                    "unicode": f"U+{ord(glyph):04X}",
                    "code": code.hex().upper(),
                    "ink_width": metric["ink_width"],
                    "ink_height": metric["ink_height"],
                    "advance": metric["advance"],
                    "core": "yes" if glyph in strict_core else "no",
                    "fallback": "module_glyph",
                }
            )

        expanded_path = directory / "glyphs_expanded32.bin"
        packed_path = directory / "glyphs_packed18.bin"
        map_path = directory / "glyph_map.csv"
        fallback_path = directory / "fallback.json"
        expanded_path.write_bytes(expanded_pool)
        packed_path.write_bytes(packed_pool)
        write_csv(
            map_path,
            [
                "index", "character", "unicode", "code", "ink_width",
                "ink_height", "advance", "core", "fallback",
            ],
            map_rows,
        )
        fallback = {
            "format": "ZIRIA-Z7-FALLBACK",
            "version": 1,
            "custom_code_rule": "EB..EF lead; 40..7E or 80..FC trail",
            "mapped_hangul": "module_glyph",
            "unmapped_hangul": "BUILD_ERROR",
            "non_hangul_double_byte": "BIOS_EX_GETFNT",
            "single_byte_and_controls": "original_renderer_path",
        }
        fallback_path.write_text(
            json.dumps(fallback, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        packed_bytes = len(packed_pool)
        expanded_bytes = len(expanded_pool)
        map_bytes = len(glyphs) * MAP_BYTES_PER_GLYPH
        metric_bytes = len(glyphs) * METRIC_BYTES_PER_GLYPH
        estimated_packed_package = (
            PACKAGE_HEADER_BYTES + packed_bytes + map_bytes + metric_bytes
        )
        summary = {
            "package_id": package_id,
            "module_id": module_id,
            "family": family,
            "row_count": len(assignments),
            "glyph_count": len(glyphs),
            "core_glyph_count": sum(glyph in strict_core for glyph in glyphs),
            "family_specific_glyph_count": sum(glyph not in strict_core for glyph in glyphs),
            "expanded_bytes": expanded_bytes,
            "packed_bytes": packed_bytes,
            "map_bytes_estimate": map_bytes,
            "metric_bytes_estimate": metric_bytes,
            "header_bytes_estimate": PACKAGE_HEADER_BYTES,
            "estimated_packed_package_bytes": estimated_packed_package,
            "code_capacity": len(codes),
            "code_margin": len(codes) - len(glyphs),
        }
        package_summaries.append(summary)
        package_manifests.append(
            {
                **summary,
                "paths": {
                    "expanded32": str(expanded_path.relative_to(ROOT)).replace("\\", "/"),
                    "packed18": str(packed_path.relative_to(ROOT)).replace("\\", "/"),
                    "glyph_map": str(map_path.relative_to(ROOT)).replace("\\", "/"),
                    "fallback": str(fallback_path.relative_to(ROOT)).replace("\\", "/"),
                },
                "sha256": {
                    "expanded32": sha256(expanded_path),
                    "packed18": sha256(packed_path),
                    "glyph_map": sha256(map_path),
                    "fallback": sha256(fallback_path),
                },
            }
        )

    write_csv(
        PACKAGE_SUMMARY,
        list(package_summaries[0].keys()),
        package_summaries,
    )
    membership_rows = []
    for glyph in global_glyphs:
        present_families = sorted(family for family, glyphs in family_sets.items() if glyph in glyphs)
        membership_rows.append(
            {
                "character": glyph,
                "unicode": f"U+{ord(glyph):04X}",
                "occurrences": global_counter[glyph],
                "families": "|".join(present_families),
                "family_count": len(present_families),
                "package_instances": glyph_package_counts[glyph],
                "strict_core": "yes" if glyph in strict_core else "no",
                "all_family_core": "yes" if glyph in all_family_core else "no",
                "ink_width": metrics[glyph]["ink_width"],
                "ink_height": metrics[glyph]["ink_height"],
                "advance": metrics[glyph]["advance"],
            }
        )
    write_csv(
        GLYPH_MEMBERSHIP,
        list(membership_rows[0].keys()),
        membership_rows,
    )

    slot_topology = json.loads(SLOT_TOPOLOGY.read_text(encoding="utf-8"))
    overlay_topology = json.loads(OVERLAY_TOPOLOGY.read_text(encoding="utf-8"))
    control_mismatches = [
        row["id"]
        for row in rows
        if CONTROL_RE.findall(row["original"]) != CONTROL_RE.findall(row["translation"])
    ]
    needs_review_ids = [row["id"] for row in rows if row["status"] == "needs_review"]
    duplicated_instances = sum(glyph_package_counts.values()) - len(global_glyphs)
    manifest = {
        "format": "ZIRIA-Z7-MODULE-GLYPH-PACKAGES",
        "version": 1,
        "task": "Z7",
        "status": (
            "PASS_WITH_TRANSLATION_REVIEW_BLOCKERS"
            if needs_review_ids or control_mismatches
            else "PASS"
        ),
        "scope": "analysis and generated package inputs only; no CUE/BIN mutation",
        "inputs": {
            "master_text": {
                "path": "translation/full_extraction/master_text.csv",
                "sha256": sha256(MASTER),
                "rows": len(rows),
            },
            "font_policy": {
                "path": "translation/font_build_policy.json",
                "sha256": sha256(FONT_POLICY),
            },
            "font": {
                "path": "font/Galmuri8x8.ttf",
                "sha256": sha256(FONT),
            },
            "slot_topology": {
                "path": "translation/slot_topology.json",
                "sha256": sha256(SLOT_TOPOLOGY),
                "logical_entries": len(slot_topology["logical_entries"]),
            },
            "overlay_topology": {
                "path": "translation/overlay_topology.json",
                "sha256": sha256(OVERLAY_TOPOLOGY),
                "logical_entries": len(overlay_topology["entries"]),
            },
        },
        "classification": {
            "storage_axis": "master_text.region: slotNN -> scene.slotNN; other regions -> shared.<region>",
            "renderer_axis": FAMILY_BY_CATEGORY,
            "core_families": list(CORE_FAMILIES),
            "strict_core_definition": "intersection of Hangul used by all four core renderer families",
            "limitation": (
                "Static CSV evidence does not prove runtime field/tower ownership for every row. "
                "Storage module and renderer family remain separate until Z8 relocation."
            ),
        },
        "font_profile": {
            **policy["render_profile"],
            "packed18": "six 24-bit pairs encoding twelve 12-bit rows",
            "advance": 12,
            "missing_glyph": "build failure",
        },
        "code_map": {
            "leads": ["EB", "EC", "ED", "EE", "EF"],
            "trail_rule": "40..7E or 80..FC",
            "capacity_per_package": len(codes),
            "mapping": "sorted Unicode order, package-local",
            "fallback": "non-Hangul double-byte codes use BIOS EX_GETFNT",
        },
        "translation_audit": {
            "needs_review_rows": len(needs_review_ids),
            "needs_review_ids": needs_review_ids,
            "control_mismatch_rows": len(control_mismatches),
            "control_mismatch_ids": control_mismatches,
            "empty_translation_rows": sum(not row["translation"].strip() for row in rows),
        },
        "inventory": {
            "global_unique_hangul": len(global_glyphs),
            "hangul_occurrences": sum(global_counter.values()),
            "renderer_families": {
                family: {
                    "rows": len(family_rows[family]),
                    "unique_hangul": len(family_sets[family]),
                    "strict_core": len(family_sets[family] & strict_core),
                    "family_specific": len(family_sets[family] - strict_core),
                }
                for family in sorted(family_rows)
            },
            "strict_core_glyphs": "".join(sorted(strict_core)),
            "strict_core_count": len(strict_core),
            "all_family_core_glyphs": "".join(sorted(all_family_core)),
            "all_family_core_count": len(all_family_core),
        },
        "duplication": {
            "package_count": len(package_manifests),
            "unique_global_glyphs": len(global_glyphs),
            "total_package_glyph_instances": sum(glyph_package_counts.values()),
            "duplicated_glyph_instances": duplicated_instances,
            "replication_bytes_expanded32": duplicated_instances * 32,
            "replication_bytes_packed18": duplicated_instances * 18,
            "policy": "ALLOW_DISK_REPLICATION; NO_GLOBAL_RESIDENT_GLYPH_POOL",
        },
        "size_summary": {
            "largest_package_glyphs": max(item["glyph_count"] for item in package_summaries),
            "largest_packed_package_bytes_estimate": max(
                item["estimated_packed_package_bytes"] for item in package_summaries
            ),
            "total_expanded_bytes": sum(item["expanded_bytes"] for item in package_summaries),
            "total_packed_bytes": sum(item["packed_bytes"] for item in package_summaries),
            "packages_over_code_capacity": sum(item["code_margin"] < 0 for item in package_summaries),
        },
        "outputs": {
            "package_root": str(PACKAGE_ROOT.relative_to(ROOT)).replace("\\", "/"),
            "package_summary": str(PACKAGE_SUMMARY.relative_to(ROOT)).replace("\\", "/"),
            "glyph_membership": str(GLYPH_MEMBERSHIP.relative_to(ROOT)).replace("\\", "/"),
            "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        },
        "packages": package_manifests,
        "next_gate": (
            "Z8 must bind each generated package to a proven loader-owned extension and "
            "relocate text without relying on cross-family RAM."
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    largest = sorted(
        package_summaries,
        key=lambda item: (-item["estimated_packed_package_bytes"], item["package_id"]),
    )[:15]
    report_lines = [
        "# Z7 모듈별 글리프 패키지",
        "",
        "이 보고서는 `master_text.csv`와 Galmuri8x8에서 재현 가능하게 생성되며 "
        "CUE/BIN을 수정하지 않는다.",
        "",
        "## 결과",
        "",
        f"- 상태: `{manifest['status']}`",
        f"- 전체 고유 한글: **{len(global_glyphs)}자**",
        f"- 렌더러 4-family 엄격 공통 코어: **{len(strict_core)}자** "
        f"(`{''.join(sorted(strict_core))}`)",
        f"- 모듈/family 로컬 패키지: **{len(package_manifests)}개**",
        f"- 최대 패키지: **{manifest['size_summary']['largest_package_glyphs']}자**, "
        f"packed 추정 **{manifest['size_summary']['largest_packed_package_bytes_estimate']}바이트**",
        f"- 중복 글리프 인스턴스: **{duplicated_instances}개** "
        f"(packed18 중복 비용 {duplicated_instances * 18}바이트)",
        f"- 코드 용량 초과 패키지: **{manifest['size_summary']['packages_over_code_capacity']}개**",
        "",
        "엄격 공통 코어는 `dialogue_event`, `menu_memo_system`, `battle`, "
        "`visual_event_portrait` 네 family 모두에서 실제 사용되는 글자의 교집합이다. "
        "공통 글리프라도 전역 RAM을 참조하지 않고 필요한 로컬 패키지에 복제한다.",
        "",
        "## Family 수요",
        "",
        "| Family | 행 | 고유 한글 | 공통 코어 | Family 전용/비공통 |",
        "|---|---:|---:|---:|---:|",
    ]
    for family, item in manifest["inventory"]["renderer_families"].items():
        report_lines.append(
            f"| `{family}` | {item['rows']} | {item['unique_hangul']} | "
            f"{item['strict_core']} | {item['family_specific']} |"
        )
    report_lines.extend(
        [
            "",
            "## 큰 패키지 상위 15개",
            "",
            "| Package | 글리프 | packed18 | 맵+metric+header 포함 추정 | 코드 여유 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for item in largest:
        report_lines.append(
            f"| `{item['package_id']}` | {item['glyph_count']} | "
            f"{item['packed_bytes']} | {item['estimated_packed_package_bytes']} | "
            f"{item['code_margin']} |"
        )
    report_lines.extend(
        [
            "",
            "## 차단 항목과 다음 게이트",
            "",
            f"- `needs_review`: {len(needs_review_ids)}행",
            f"- 원문/번역 제어코드 불일치: {len(control_mismatches)}행",
            "- 위 항목은 용량 산정에서 제외하지 않았지만 릴리스 입력으로 승인되지 않는다.",
            "- 정적 CSV만으로 모든 행의 field/tower 런타임 소유권을 확정하지 않는다. "
            "Z8에서 로더가 소유하는 extension과 문자열 컨테이너를 결합해야 한다.",
            "- 모든 패키지는 미매핑 한글을 빌드 오류로 처리하고, 비한글 2바이트 문자는 "
            "원본 BIOS `EX_GETFNT`로 fallback한다.",
            "",
            "## 산출물",
            "",
            f"- Manifest: `{MANIFEST.relative_to(ROOT).as_posix()}`",
            f"- 패키지 요약: `{PACKAGE_SUMMARY.relative_to(ROOT).as_posix()}`",
            f"- 글리프 membership: `{GLYPH_MEMBERSHIP.relative_to(ROOT).as_posix()}`",
            f"- 바이너리/맵 패키지: `{PACKAGE_ROOT.relative_to(ROOT).as_posix()}`",
            f"- 생성기: `{Path(__file__).relative_to(ROOT).as_posix()}`",
            "",
        ]
    )
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST.relative_to(ROOT)),
                "status": manifest["status"],
                "global_unique_hangul": len(global_glyphs),
                "strict_core_count": len(strict_core),
                "packages": len(package_manifests),
                "largest_package_glyphs": manifest["size_summary"]["largest_package_glyphs"],
                "largest_packed_package_bytes_estimate": manifest["size_summary"][
                    "largest_packed_package_bytes_estimate"
                ],
                "duplicated_glyph_instances": duplicated_instances,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
