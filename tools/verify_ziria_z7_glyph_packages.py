#!/usr/bin/env python3
"""Independently verify Z7 generated glyph packages and their input identity."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_z7_glyph_packages_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Z7 VERIFY FAIL: {message}")


def expand(packed: bytes) -> bytes:
    require(len(packed) == 18, "packed record length")
    output = bytearray()
    for index in range(0, 18, 3):
        byte0, byte1, byte2 = packed[index:index + 3]
        output.extend(
            (
                byte0,
                byte1 & 0xF0,
                ((byte1 & 0x0F) << 4) | (byte2 >> 4),
                (byte2 & 0x0F) << 4,
            )
        )
    output.extend(bytes(8))
    return bytes(output)


def valid_code(code: str) -> bool:
    raw = bytes.fromhex(code)
    return (
        len(raw) == 2
        and 0xEB <= raw[0] <= 0xEF
        and (0x40 <= raw[1] <= 0x7E or 0x80 <= raw[1] <= 0xFC)
    )


def main() -> None:
    require(MANIFEST.is_file(), "manifest missing")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(data["format"] == "ZIRIA-Z7-MODULE-GLYPH-PACKAGES", "format")
    require(data["scope"].endswith("no CUE/BIN mutation"), "scope")
    for item in data["inputs"].values():
        path = ROOT / item["path"]
        require(path.is_file(), f"input missing: {path}")
        require(sha256(path) == item["sha256"], f"input hash: {path}")

    packages = data["packages"]
    require(len(packages) == data["duplication"]["package_count"], "package count")
    total_instances = 0
    largest = 0
    for package in packages:
        paths = {name: ROOT / path for name, path in package["paths"].items()}
        for name, path in paths.items():
            require(path.is_file(), f"{package['package_id']} missing {name}")
            require(
                sha256(path) == package["sha256"][name],
                f"{package['package_id']} hash {name}",
            )
        with paths["glyph_map"].open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        glyph_count = package["glyph_count"]
        require(len(rows) == glyph_count, f"{package['package_id']} map count")
        require(
            [int(row["index"]) for row in rows] == list(range(glyph_count)),
            f"{package['package_id']} contiguous indexes",
        )
        require(len({row["character"] for row in rows}) == glyph_count, "duplicate glyph")
        require(len({row["code"] for row in rows}) == glyph_count, "duplicate code")
        require(all(valid_code(row["code"]) for row in rows), "invalid local code")
        require(all(int(row["advance"]) == 12 for row in rows), "advance")
        expanded = paths["expanded32"].read_bytes()
        packed = paths["packed18"].read_bytes()
        require(len(expanded) == glyph_count * 32, "expanded size")
        require(len(packed) == glyph_count * 18, "packed size")
        for index in range(glyph_count):
            require(
                expand(packed[index * 18:(index + 1) * 18])
                == expanded[index * 32:(index + 1) * 32],
                f"{package['package_id']} packed round trip index {index}",
            )
        total_instances += glyph_count
        largest = max(largest, glyph_count)

    require(
        total_instances == data["duplication"]["total_package_glyph_instances"],
        "total glyph instances",
    )
    require(largest == data["size_summary"]["largest_package_glyphs"], "largest package")
    require(data["size_summary"]["packages_over_code_capacity"] == 0, "code overflow")
    output_root = ROOT / data["outputs"]["package_root"]
    require(not list(output_root.rglob("*.cue")), "unexpected CUE output")
    require(not list(output_root.rglob("*.bin")) or all(
        path.name in {"glyphs_expanded32.bin", "glyphs_packed18.bin"}
        for path in output_root.rglob("*.bin")
    ), "unexpected non-glyph BIN output")
    print(
        "Z7 GLYPH PACKAGES: PASS "
        f"({len(packages)} packages, {total_instances} instances, max {largest} glyphs)"
    )


if __name__ == "__main__":
    main()
