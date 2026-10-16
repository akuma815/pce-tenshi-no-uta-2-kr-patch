#!/usr/bin/env python3
"""Z2 identity extraction and rebuild for the mixed-mode PCE CD image.

Track 02 is partitioned into non-overlapping binary segments derived from both
loader directories.  Logical module views are extracted separately.  The full
BIN is rebuilt by streaming the untouched raw audio spans around the rebuilt
Track 02, without ever modifying the source image.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
Z1 = ROOT / "translation" / "ziria_module_catalog.json"
BUILD_ROOT = ROOT / "module_relink"
SEGMENT_DIR = BUILD_ROOT / "track02" / "segments"
LOGICAL_DIR = BUILD_ROOT / "track02" / "logical_modules"
SEMANTIC_DIR = BUILD_ROOT / "track02" / "semantic_modules"
OUTPUT_DIR = BUILD_ROOT / "output"
REBUILT_TRACK02 = BUILD_ROOT / "track02" / "Track02_data.identity.iso"
OUTPUT_BIN = OUTPUT_DIR / BIN.name
OUTPUT_CUE = OUTPUT_DIR / CUE.name
MANIFEST = ROOT / "translation" / "ziria_identity_rebuild.json"
LINKER_LAYOUT = BUILD_ROOT / "linker_layout.json"

EXPECTED_BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_CUE_SHA256 = "C491342EA8CBF2B6E829316AAAD0AF3F790EC58288DE9BF880927CDCC7C9CC6B"
EXPECTED_TRACK02_SHA256 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"
DATA_TRACK_NUMBER = 2
SECTOR_SIZES = {"AUDIO": 2352, "MODE1/2048": 2048, "MODE1/2352": 2352}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def parse_cue() -> list[dict]:
    tracks: list[dict] = []
    for line in CUE.read_text(encoding="ascii").splitlines():
        track_match = re.match(r"\s*TRACK\s+(\d+)\s+(\S+)", line)
        if track_match:
            tracks.append({
                "number": int(track_match.group(1)),
                "type": track_match.group(2),
                "index_frame": None,
            })
            continue
        index_match = re.match(r"\s*INDEX\s+01\s+(\d+):(\d+):(\d+)", line)
        if index_match:
            minutes, seconds, frames = map(int, index_match.groups())
            tracks[-1]["index_frame"] = (minutes * 60 + seconds) * 75 + frames

    if not tracks or any(x["index_frame"] is None for x in tracks):
        raise ValueError("CUE has an incomplete track/index declaration")

    source_size = BIN.stat().st_size
    file_offset = 0
    for index, track in enumerate(tracks):
        sector_size = SECTOR_SIZES[track["type"]]
        if index + 1 < len(tracks):
            sector_count = tracks[index + 1]["index_frame"] - track["index_frame"]
        else:
            remaining = source_size - file_offset
            if remaining % sector_size:
                raise ValueError("last track does not consume the BIN exactly")
            sector_count = remaining // sector_size
        byte_length = sector_count * sector_size
        track.update({
            "sector_size": sector_size,
            "sector_count": sector_count,
            "file_offset": file_offset,
            "byte_length": byte_length,
            "file_end": file_offset + byte_length,
        })
        file_offset += byte_length

    if file_offset != source_size:
        raise ValueError(f"CUE-derived end {file_offset} != BIN size {source_size}")
    return tracks


def read_range(offset: int, length: int) -> bytes:
    with BIN.open("rb") as source:
        source.seek(offset)
        data = source.read(length)
    if len(data) != length:
        raise EOFError(f"short source read at {offset} length {length}")
    return data


def write_if_changed(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size == len(data) and sha256(path) == sha256_bytes(data):
        return
    path.write_bytes(data)


def copy_span(source, output, length: int) -> None:
    remaining = length
    while remaining:
        block = source.read(min(4 * 1024 * 1024, remaining))
        if not block:
            raise EOFError("unexpected end while rebuilding BIN")
        output.write(block)
        remaining -= len(block)


def main() -> None:
    if sha256(BIN) != EXPECTED_BIN_SHA256:
        raise ValueError("original BIN identity mismatch")
    if sha256(CUE) != EXPECTED_CUE_SHA256:
        raise ValueError("original CUE identity mismatch")

    z1 = json.loads(Z1.read_text(encoding="utf-8"))
    if z1["source"]["sha256"] != EXPECTED_BIN_SHA256:
        raise ValueError("Z1 catalogue belongs to another source image")
    tracks = parse_cue()
    data_track = next(x for x in tracks if x["number"] == DATA_TRACK_NUMBER)
    if data_track["type"] != "MODE1/2048":
        raise ValueError("Track 02 is not MODE1/2048")
    track02_offset = data_track["file_offset"]
    track02_size = data_track["byte_length"]
    sector_size = data_track["sector_size"]

    boundaries = {0, track02_size}
    owners: list[dict] = []
    for directory_name in ("primary", "overlay"):
        for entry in z1["directories"][directory_name]["entries"]:
            start = entry["lba"] * sector_size
            end = start + entry["sector_count"] * sector_size
            if not 0 <= start < end <= track02_size:
                raise ValueError(f"{directory_name} entry outside Track02: {entry}")
            boundaries.update((start, end))
            owners.append({
                "id": f"{directory_name}.{entry['logical_entry']:02d}",
                "kind": "loader_directory_entry",
                "directory": directory_name,
                "logical_entry": entry["logical_entry"],
                "lba": entry["lba"],
                "sector_count": entry["sector_count"],
                "start": start,
                "end": end,
            })

    for item in z1["modules"]:
        if item["lba"] is None:
            continue
        start = item["lba"] * sector_size
        end = start + item["sector_count"] * sector_size
        if not 0 <= start < end <= track02_size:
            raise ValueError(f"semantic module outside Track02: {item['id']}")
        boundaries.update((start, end))
        owners.append({
            "id": item["id"],
            "kind": item["module_kind"],
            "lba": item["lba"],
            "sector_count": item["sector_count"],
            "start": start,
            "end": end,
        })

    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    LOGICAL_DIR.mkdir(parents=True, exist_ok=True)
    SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ordered = sorted(boundaries)
    segments = []
    for index, (start, end) in enumerate(zip(ordered, ordered[1:])):
        if start == end:
            continue
        data = read_range(track02_offset + start, end - start)
        filename = f"seg_{index:03d}_{start // sector_size:04d}_{end // sector_size:04d}.bin"
        path = SEGMENT_DIR / filename
        write_if_changed(path, data)
        segments.append({
            "index": index,
            "path": path.relative_to(ROOT).as_posix(),
            "track02_offset": start,
            "length": end - start,
            "start_lba": start // sector_size,
            "end_lba_exclusive": end // sector_size,
            "sha256": sha256_bytes(data),
            "owners": sorted(x["id"] for x in owners if x["start"] <= start and end <= x["end"]),
        })

    logical_modules = []
    for owner in owners:
        if owner["kind"] != "loader_directory_entry":
            continue
        data = read_range(track02_offset + owner["start"], owner["end"] - owner["start"])
        filename = (
            f"{owner['directory']}_{owner['logical_entry']:02d}_"
            f"lba{owner['lba']:04d}_s{owner['sector_count']:02d}.bin"
        )
        path = LOGICAL_DIR / filename
        write_if_changed(path, data)
        logical_modules.append({
            **{k: owner[k] for k in ("id", "directory", "logical_entry", "lba", "sector_count")},
            "path": path.relative_to(ROOT).as_posix(),
            "size": len(data),
            "sha256": sha256_bytes(data),
        })

    semantic_modules = []
    for owner in owners:
        if owner["kind"] == "loader_directory_entry":
            continue
        data = read_range(track02_offset + owner["start"], owner["end"] - owner["start"])
        safe_id = owner["id"].replace("/", "_")
        filename = f"{safe_id}_lba{owner['lba']:04d}_s{owner['sector_count']:02d}.bin"
        path = SEMANTIC_DIR / filename
        write_if_changed(path, data)
        semantic_modules.append({
            **{k: owner[k] for k in ("id", "kind", "lba", "sector_count")},
            "path": path.relative_to(ROOT).as_posix(),
            "size": len(data),
            "sha256": sha256_bytes(data),
        })

    track02_tmp = REBUILT_TRACK02.with_suffix(".tmp")
    with track02_tmp.open("wb") as output:
        for segment in segments:
            with (ROOT / segment["path"]).open("rb") as source:
                copy_span(source, output, segment["length"])
    track02_tmp.replace(REBUILT_TRACK02)
    rebuilt_track02_hash = sha256(REBUILT_TRACK02)
    if REBUILT_TRACK02.stat().st_size != track02_size or rebuilt_track02_hash != EXPECTED_TRACK02_SHA256:
        raise ValueError("Track02 identity rebuild mismatch")

    output_tmp = OUTPUT_BIN.with_suffix(".tmp")
    with BIN.open("rb") as source, output_tmp.open("wb") as output:
        copy_span(source, output, track02_offset)
        with REBUILT_TRACK02.open("rb") as rebuilt:
            copy_span(rebuilt, output, track02_size)
        source.seek(track02_offset + track02_size)
        copy_span(source, output, BIN.stat().st_size - track02_offset - track02_size)
    output_tmp.replace(OUTPUT_BIN)
    shutil.copyfile(CUE, OUTPUT_CUE)

    output_bin_hash = sha256(OUTPUT_BIN)
    output_cue_hash = sha256(OUTPUT_CUE)
    if output_bin_hash != EXPECTED_BIN_SHA256:
        raise ValueError(f"full BIN identity mismatch: {output_bin_hash}")
    if output_cue_hash != EXPECTED_CUE_SHA256:
        raise ValueError(f"CUE identity mismatch: {output_cue_hash}")

    manifest = {
        "format": "ZIRIA-Z2-IDENTITY-REBUILD",
        "version": 1,
        "status": "PASS",
        "source": {
            "bin": BIN.name,
            "size": BIN.stat().st_size,
            "sha256": EXPECTED_BIN_SHA256,
            "cue": CUE.name,
            "cue_sha256": EXPECTED_CUE_SHA256,
        },
        "cue_tracks": tracks,
        "track02": {
            "file_offset": track02_offset,
            "size": track02_size,
            "sector_size": sector_size,
            "sector_count": data_track["sector_count"],
            "expected_sha256": EXPECTED_TRACK02_SHA256,
            "rebuilt_path": REBUILT_TRACK02.relative_to(ROOT).as_posix(),
            "rebuilt_sha256": rebuilt_track02_hash,
            "partition_segment_count": len(segments),
            "partition_coverage_bytes": sum(x["length"] for x in segments),
            "segments": segments,
        },
        "logical_modules": logical_modules,
        "semantic_modules": semantic_modules,
        "output": {
            "bin": OUTPUT_BIN.relative_to(ROOT).as_posix(),
            "bin_size": OUTPUT_BIN.stat().st_size,
            "bin_sha256": output_bin_hash,
            "cue": OUTPUT_CUE.relative_to(ROOT).as_posix(),
            "cue_sha256": output_cue_hash,
        },
        "identity_guarantees": {
            "track02_partition_is_non_overlapping": True,
            "track02_partition_is_gapless": True,
            "raw_audio_bytes_are_streamed_unchanged": True,
            "cue_bytes_are_identical": True,
            "full_bin_bytes_are_identical": True,
            "source_disc_was_modified": False,
        },
    }
    linker_layout = {
        "format": "ZIRIA-MODULE-LINKER-LAYOUT",
        "version": 1,
        "address_model": "HuC6280 8 KiB physical banks; CPU address is valid only with the listed MPR mapping",
        "immutable_source_sha256": EXPECTED_BIN_SHA256,
        "modules": [
            {
                "id": item["id"],
                "kind": item["module_kind"],
                "family": item["family"],
                "lba": item["lba"],
                "sector_count": item["sector_count"],
                "physical_bank_interval": item["physical_bank_interval"],
                "runtime_range": item["runtime_range"],
                "entry_point": item["entry_point"],
                "identity_binary": next(
                    (x["path"] for x in semantic_modules if x["id"] == item["id"]), None
                ),
                "z3_section_policy": (
                    "linkable_executable" if item["module_kind"] == "executable_engine"
                    else "opaque_resource_or_scene_package"
                ),
            }
            for item in z1["modules"] if item["lba"] is not None
        ],
        "reserved_transition_window": {
            "physical_banks": "0x68-0x7F",
            "size_bytes": 96 * 2048,
            "policy": "fully replaced by each scene load; no cross-family persistent section",
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LINKER_LAYOUT.write_text(json.dumps(linker_layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS Track02 identity: {rebuilt_track02_hash}")
    print(f"PASS full BIN identity: {output_bin_hash}")
    print(f"PASS CUE identity: {output_cue_hash}")
    print(f"partition segments: {len(segments)}")
    print(f"logical modules: {len(logical_modules)}")
    print(f"semantic modules: {len(semantic_modules)}")
    print(MANIFEST)
    print(LINKER_LAYOUT)


if __name__ == "__main__":
    main()
