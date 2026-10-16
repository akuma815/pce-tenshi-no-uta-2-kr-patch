#!/usr/bin/env python3
"""Independently verify the non-runtime Ziria Z8 text containers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z8_text_containers_manifest.json"
TOKEN_RE = re.compile(r"\\[np]|\{[^{}]+\}")
BANK = 8192


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(manifest["format"] == "ZIRIA-Z8-TEXT-CONTAINERS", "manifest format")
    require(manifest["status"] == "STRUCTURE_PASS_RELOCATION_BLOCKED", "unsafe status")

    for item in manifest["inputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"missing input: {path}")
        require(sha256(path) == item["sha256"], f"input hash: {path}")

    iso_path = ROOT / manifest["inputs"]["track02_iso"]["path"]
    iso = iso_path.read_bytes()
    index_path = ROOT / manifest["outputs"]["entry_index"]
    index_rows = read_csv(index_path)
    require(len(index_rows) == 18817, "entry count")
    require(len({row["id"] for row in index_rows}) == len(index_rows), "stable ID uniqueness")
    require(
        [int(row["iso_offset"], 16) for row in index_rows]
        == sorted(int(row["iso_offset"], 16) for row in index_rows),
        "entry order",
    )

    indexed = {row["id"]: row for row in index_rows}
    package_rows: dict[str, list[dict]] = defaultdict(list)
    for row in index_rows:
        raw = bytes.fromhex(row["raw_hex"])
        offset = int(row["iso_offset"], 16)
        encoded = bytes.fromhex(row["encoded_hex"])
        require(iso[offset:offset + len(raw)] == raw, f"raw ISO mismatch: {row['id']}")
        require(raw[-1:] == b"\x00", f"raw terminator: {row['id']}")
        require(encoded[-1:] == b"\x00", f"encoded terminator: {row['id']}")
        require(encoded[:-1].find(b"\x00") < 0, f"embedded encoded NUL: {row['id']}")
        require(
            TOKEN_RE.findall(row["original"]) == TOKEN_RE.findall(row["translation"]),
            f"token sequence: {row['id']}",
        )
        require(
            hashlib.sha256(encoded).hexdigest().upper() == row["encoded_sha256"],
            f"encoded hash: {row['id']}",
        )
        package_rows[row["package_id"]].append(row)

    containers = manifest["containers"]
    require(len(containers) == manifest["population"]["container_count"], "container count")
    require({item["package_id"] for item in containers} == set(package_rows), "package coverage")
    for item in containers:
        paths = {key: ROOT / value for key, value in item["paths"].items()}
        for key, path in paths.items():
            require(path.is_file(), f"missing container file: {path}")
            require(sha256(path) == item["sha256"][key], f"container hash: {path}")
        profile = json.loads(paths["profile"].read_text(encoding="utf-8"))
        require(profile["runtime_status"] == "NOT_LINKED_ANALYSIS_CONTAINER", "runtime status")
        pool = paths["strings"].read_bytes()
        local_rows = read_csv(paths["entries"])
        require(len(local_rows) == item["row_count"], f"local row count: {item['package_id']}")
        require({row["id"] for row in local_rows} == {row["id"] for row in package_rows[item["package_id"]]}, "local coverage")
        offset_payload: dict[int, bytes] = {}
        for row in local_rows:
            offset = int(row["container_offset"], 16)
            encoded = bytes.fromhex(row["encoded_hex"])
            require(pool[offset:offset + len(encoded)] == encoded, f"pool slice: {row['id']}")
            require(
                offset // BANK == (offset + len(encoded) - 1) // BANK,
                f"8 KiB crossing: {row['id']}",
            )
            if offset in offset_payload:
                require(offset_payload[offset] == encoded, f"invalid dedup: {row['id']}")
            else:
                offset_payload[offset] = encoded
            require(indexed[row["id"]]["encoded_hex"] == row["encoded_hex"], f"global/local: {row['id']}")

    semantic_tables = manifest["semantic_tables"]
    semantic_ids = []
    for table in semantic_tables:
        path = ROOT / table["path"]
        require(path.is_file(), f"missing semantic table: {path}")
        require(sha256(path) == table["sha256"], f"semantic hash: {path}")
        rows = read_csv(path)
        require(len(rows) == table["rows"], f"semantic row count: {path}")
        require(all(row["category"] == table["category"] for row in rows), f"semantic category: {path}")
        require(all(row["subcategory"] == table["subcategory"] for row in rows), f"semantic subcategory: {path}")
        semantic_ids.extend(row["id"] for row in rows)
    require(sorted(semantic_ids) == sorted(indexed), "semantic table coverage")

    output_root = ROOT / "module_relink" / "z8_text_containers"
    require(not list(output_root.rglob("*.cue")), "CUE created inside Z8 output")
    require(
        all(path.name == "strings.bin" for path in output_root.rglob("*.bin")),
        "unexpected BIN inside Z8 output",
    )
    require(manifest["encoding_audit"]["unmapped_characters"] == 0, "unmapped characters")
    require(manifest["encoding_audit"]["cross_bank_strings"] == 0, "manifest crossing")

    print(
        json.dumps(
            {
                "status": "PASS",
                "rows": len(index_rows),
                "containers": len(containers),
                "semantic_tables": len(semantic_tables),
                "encoding_alias_rows": manifest["encoding_audit"]["encoding_alias_rows"],
                "encoding_alias_occurrences": manifest["encoding_audit"]["encoding_alias_occurrences"],
                "runtime_linked": False,
                "disc_mutated": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
