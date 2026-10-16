#!/usr/bin/env python3
"""Create the Z3 fail-closed module section/link contract.

This is the WLA-equivalent orchestration layer used before any assembly source
exists.  It preserves each identity module as an immutable `original` section,
declares future extension sections, and refuses every non-zero extension unless
disc allocation and owning-loader registration are approved together.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
Z1_PATH = ROOT / "translation" / "ziria_module_catalog.json"
Z2_PATH = ROOT / "translation" / "ziria_identity_rebuild.json"
LAYOUT_PATH = ROOT / "module_relink" / "linker_layout.json"
SPEC_DIR = ROOT / "module_relink" / "specs"
LINKED_DIR = ROOT / "module_relink" / "linked_identity"
REGISTRY_PATH = ROOT / "module_relink" / "extension_registry.json"
RESULT_PATH = ROOT / "translation" / "ziria_section_link_result.json"
EXPECTED_BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
SECTION_KINDS = ("original", "extension_code", "text", "glyph", "relocation")
PROHIBITED_STORAGE = {"work_ram", "implicit_gap", "fill_run", "auto_sidecar", "shared_scene_bank"}


class LinkContractError(ValueError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def validate_extension_request(request: dict, registry: dict) -> dict:
    """Validate one future non-zero section request or raise LinkContractError."""
    required = {"module_id", "family", "section_type", "payload_size", "storage", "lifetime"}
    missing = sorted(required - request.keys())
    if missing:
        raise LinkContractError(f"missing request fields: {missing}")
    if request["section_type"] not in SECTION_KINDS[1:]:
        raise LinkContractError("extension request uses an invalid section type")
    if not isinstance(request["payload_size"], int) or request["payload_size"] <= 0:
        raise LinkContractError("extension payload must be non-zero")

    storage = request["storage"]
    if storage.get("kind") in PROHIBITED_STORAGE:
        raise LinkContractError(f"prohibited storage strategy: {storage.get('kind')}")
    if storage.get("kind") != "registered_translation_module":
        raise LinkContractError("non-zero extension requires a registered translation module")
    if request["lifetime"] != "owning_family_only":
        raise LinkContractError("cross-family persistent lifetime is prohibited")
    if storage.get("physical_banks") == "0x68-0x7F" and request["lifetime"] != "owning_family_only":
        raise LinkContractError("scene replacement banks cannot persist across families")

    allocation_id = storage.get("allocation_id")
    allocations = {x["id"]: x for x in registry["approved_allocations"]}
    if allocation_id not in allocations:
        raise LinkContractError("disc allocation is not approved")
    allocation = allocations[allocation_id]
    if allocation["family"] != request["family"] or allocation["owner_module"] != request["module_id"]:
        raise LinkContractError("allocation ownership does not match the requesting module")
    if allocation["capacity_bytes"] < request["payload_size"]:
        raise LinkContractError("extension exceeds its approved sector allocation")
    registration = allocation.get("loader_registration")
    if not registration or not registration.get("table_patch") or not registration.get("load_condition"):
        raise LinkContractError("allocation and owning-loader registration must be approved atomically")
    return allocation


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def section_set(original_size: int | None, original_path: str | None) -> list[dict]:
    return [
        {
            "name": "original",
            "kind": "original",
            "size": original_size,
            "source": original_path,
            "placement": "fixed_identity",
            "mutable": False,
        },
        *[
            {
                "name": name,
                "kind": name,
                "size": 0,
                "source": None,
                "placement": "unallocated",
                "mutable": True,
                "nonzero_gate": "approved disc allocation + owning-loader registration",
            }
            for name in SECTION_KINDS[1:]
        ],
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=Path, help="optional future extension request JSON")
    args = parser.parse_args()

    z1 = load_json(Z1_PATH)
    z2 = load_json(Z2_PATH)
    layout = load_json(LAYOUT_PATH)
    if z1["source"]["sha256"] != EXPECTED_BIN_SHA256 or z2["source"]["sha256"] != EXPECTED_BIN_SHA256:
        raise LinkContractError("Z1/Z2 source identity mismatch")
    if layout["immutable_source_sha256"] != EXPECTED_BIN_SHA256:
        raise LinkContractError("linker layout source identity mismatch")

    registry = {
        "format": "ZIRIA-EXTENSION-REGISTRY",
        "version": 1,
        "status": "LOCKED_EMPTY_AT_Z3",
        "approved_allocations": [],
        "transaction_rule": (
            "A non-zero section is legal only when sector allocation and the owning loader's "
            "table patch/load condition are approved in the same registry entry."
        ),
        "prohibited": sorted(PROHIBITED_STORAGE),
        "scene_replacement_window": {
            "physical_banks": "0x68-0x7F",
            "size_bytes": 96 * 2048,
            "persistent_across_family_transition": False,
        },
    }
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.requests:
        requests = load_json(args.requests).get("requests", [])
        for request in requests:
            validate_extension_request(request, registry)

    semantic = {x["id"]: x for x in z2["semantic_modules"]}
    z1_modules = {x["id"]: x for x in z1["modules"]}
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    specs = []
    linked = []

    for module_id, item in z1_modules.items():
        source_info = semantic.get(module_id)
        source_path = source_info["path"] if source_info else None
        source_size = source_info["size"] if source_info else None
        host_candidates = []
        blocked_reason = None
        if module_id == "subrenderer.memo":
            host_candidates = ["field.main_engine", "scene.field_start"]
            blocked_reason = "runtime entry PC and exact resident host are not yet captured"
        elif module_id == "subrenderer.portrait":
            host_candidates = ["field.main_engine", "scene.field_start"]
            blocked_reason = "asset dependency on scene.field_start is proven; code entry PC is unresolved"

        spec = {
            "format": "ZIRIA-MODULE-SECTION-SPEC",
            "version": 1,
            "module_id": module_id,
            "module_kind": item["module_kind"],
            "family": item["family"],
            "disc": {"lba": item["lba"], "sector_count": item["sector_count"]},
            "runtime": {
                "physical_bank_interval": item["physical_bank_interval"],
                "runtime_range": item["runtime_range"],
                "entry_point": item["entry_point"],
                "lifetime": "owning_family_only",
            },
            "host_candidates": host_candidates,
            "extension_blocked_reason": blocked_reason,
            "sections": section_set(source_size, source_path),
            "link_policy": {
                "assembler": "WLA-HuC6280 compatible section object or equivalent byte section",
                "identity_mode": "emit original section byte-for-byte",
                "extension_mode": "requires extension_registry approved allocation",
                "cross_family_reference": "prohibited",
            },
        }
        spec_path = SPEC_DIR / f"{module_id}.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        specs.append(spec_path.relative_to(ROOT).as_posix())

        if source_info:
            source = ROOT / source_path
            output = LINKED_DIR / source.name
            shutil.copyfile(source, output)
            if digest(output) != source_info["sha256"]:
                raise LinkContractError(f"identity section link mismatch: {module_id}")
            linked.append({
                "module_id": module_id,
                "input": source_path,
                "output": output.relative_to(ROOT).as_posix(),
                "size": source_size,
                "sha256": source_info["sha256"],
                "nonzero_extension_sections": 0,
            })

    result = {
        "format": "ZIRIA-Z3-SECTION-LINK-RESULT",
        "version": 1,
        "status": "PASS_IDENTITY_SECTIONS_AND_FAIL_CLOSED_EXTENSION_GATE",
        "source_bin_sha256": EXPECTED_BIN_SHA256,
        "reference_architecture": {
            "project": "suppertails66/tenmatools/tenma",
            "adopted_principles": [
                "patch independently extracted module binaries",
                "link modules through a consolidated intermediate layout",
                "split finalized units back into loader-owned binaries",
                "perform disc insertion only after module link succeeds",
            ],
        },
        "section_kinds": list(SECTION_KINDS),
        "specs": specs,
        "linked_modules": linked,
        "virtual_subrenderers": ["subrenderer.memo", "subrenderer.portrait"],
        "extension_registry": REGISTRY_PATH.relative_to(ROOT).as_posix(),
        "approved_extension_count": len(registry["approved_allocations"]),
        "identity_guarantees": {
            "all_original_sections_immutable": True,
            "all_extension_sections_zero_length": True,
            "linked_outputs_match_identity_inputs": True,
            "unregistered_extension_fails": True,
            "work_ram_execution_fails_contract": True,
            "implicit_fill_space_fails_contract": True,
            "cross_family_persistence_fails_contract": True,
            "disc_image_modified": False,
        },
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS specs: {len(specs)}")
    print(f"PASS identity-linked modules: {len(linked)}")
    print("PASS approved non-zero extensions: 0")
    print(RESULT_PATH)


if __name__ == "__main__":
    main()
