#!/usr/bin/env python3
"""Verify Z3 identity sections and deliberately exercise rejected layouts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "translation" / "ziria_section_link_result.json"
REGISTRY = ROOT / "module_relink" / "extension_registry.json"
BUILDER = ROOT / "tools" / "build_ziria_z3_sections.py"
EXPECTED_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
SECTION_KINDS = ["original", "extension_code", "text", "glyph", "relocation"]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def load_builder():
    spec = importlib.util.spec_from_file_location("ziria_z3_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def expect_reject(builder, registry: dict, request: dict, label: str) -> None:
    try:
        builder.validate_extension_request(request, registry)
    except builder.LinkContractError:
        return
    raise AssertionError(f"unsafe layout was accepted: {label}")


def main() -> None:
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert result["source_bin_sha256"] == EXPECTED_BIN
    assert result["section_kinds"] == SECTION_KINDS
    assert result["approved_extension_count"] == 0
    assert len(result["specs"]) == 12
    assert len(result["linked_modules"]) == 10

    for relative in result["specs"]:
        spec = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        sections = spec["sections"]
        assert [x["kind"] for x in sections] == SECTION_KINDS
        assert sections[0]["mutable"] is False
        assert all(x["size"] == 0 and x["placement"] == "unallocated" for x in sections[1:])

    for linked in result["linked_modules"]:
        source = ROOT / linked["input"]
        output = ROOT / linked["output"]
        assert source.stat().st_size == output.stat().st_size == linked["size"]
        assert digest(source) == digest(output) == linked["sha256"]

    builder = load_builder()
    base = {
        "module_id": "scene.field_start",
        "family": "field",
        "section_type": "glyph",
        "payload_size": 32,
        "lifetime": "owning_family_only",
    }
    for kind in ("work_ram", "implicit_gap", "fill_run", "auto_sidecar", "shared_scene_bank"):
        expect_reject(builder, registry, {**base, "storage": {"kind": kind}}, kind)
    expect_reject(
        builder,
        registry,
        {**base, "storage": {"kind": "registered_translation_module", "allocation_id": "missing"}},
        "unregistered allocation",
    )
    expect_reject(
        builder,
        registry,
        {
            **base,
            "lifetime": "cross_family",
            "storage": {
                "kind": "registered_translation_module",
                "allocation_id": "missing",
                "physical_banks": "0x68-0x7F",
            },
        },
        "cross-family scene bank persistence",
    )

    guarantees = result["identity_guarantees"]
    assert guarantees["disc_image_modified"] is False
    assert all(value is True for key, value in guarantees.items() if key != "disc_image_modified")
    print("PASS: Z3 section identity and unsafe-layout rejection verified")
    print("rejected=7 specs=12 identity_linked=10 approved_extensions=0")


if __name__ == "__main__":
    main()
