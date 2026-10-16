#!/usr/bin/env python3
"""Fail-closed verification of the Z2 module extraction and identity rebuild."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "ziria_identity_rebuild.json"
EXPECTED_BIN = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
EXPECTED_CUE = "C491342EA8CBF2B6E829316AAAD0AF3F790EC58288DE9BF880927CDCC7C9CC6B"
EXPECTED_TRACK02 = "7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    track02 = manifest["track02"]
    segments = track02["segments"]
    assert segments
    cursor = 0
    for segment in segments:
        assert segment["track02_offset"] == cursor
        path = ROOT / segment["path"]
        assert path.stat().st_size == segment["length"]
        assert digest(path) == segment["sha256"]
        cursor += segment["length"]
    assert cursor == track02["size"] == track02["partition_coverage_bytes"]

    rebuilt_track = ROOT / track02["rebuilt_path"]
    assert rebuilt_track.stat().st_size == track02["size"]
    assert digest(rebuilt_track) == track02["rebuilt_sha256"] == EXPECTED_TRACK02

    for module in manifest["logical_modules"] + manifest["semantic_modules"]:
        path = ROOT / module["path"]
        assert path.stat().st_size == module["size"]
        assert digest(path) == module["sha256"]

    output = manifest["output"]
    output_bin = ROOT / output["bin"]
    output_cue = ROOT / output["cue"]
    assert output_bin.stat().st_size == manifest["source"]["size"]
    assert digest(output_bin) == output["bin_sha256"] == EXPECTED_BIN
    assert digest(output_cue) == output["cue_sha256"] == EXPECTED_CUE

    tracks = manifest["cue_tracks"]
    assert tracks[0]["file_offset"] == 0
    assert tracks[-1]["file_end"] == output_bin.stat().st_size
    assert all(a["file_end"] == b["file_offset"] for a, b in zip(tracks, tracks[1:]))
    assert next(x for x in tracks if x["number"] == 2)["type"] == "MODE1/2048"

    guarantees = manifest["identity_guarantees"]
    for key in (
        "track02_partition_is_non_overlapping",
        "track02_partition_is_gapless",
        "raw_audio_bytes_are_streamed_unchanged",
        "cue_bytes_are_identical",
        "full_bin_bytes_are_identical",
    ):
        assert guarantees[key] is True
    assert guarantees["source_disc_was_modified"] is False
    print("PASS: Z2 full identity rebuild and all extracted artifacts verified")
    print(
        f"segments={len(segments)} logical_modules={len(manifest['logical_modules'])} "
        f"semantic_modules={len(manifest['semantic_modules'])}"
    )


if __name__ == "__main__":
    main()
