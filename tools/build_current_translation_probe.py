#!/usr/bin/env python3
"""Build a first-dialogue Hangul probe using the current master translation.

The probe deliberately changes only three dialogue-body byte runs and the
corresponding EX_GETFNT mode-1 System Card glyph slots.  Speaker names and all
control bytes stay byte-identical to the original game.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_system_card_font_slots import glyph_index  # noqa: E402

ORIGINAL_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
ORIGINAL_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
ORIGINAL_BIOS = Path(r"H:\BizHawk\Firmware\PCECD_3.0-(J).pce")
MASTER_CSV = ROOT / "translation" / "full_extraction" / "master_text.csv"
FONT_TTF = ROOT / "font" / "Galmuri11-Condensed.ttf"

OUT_STEM = "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_current_translation_probe"
OUT_BIN = ROOT / f"{OUT_STEM}.bin"
OUT_CUE = ROOT / f"{OUT_STEM}.cue"
OUT_BIOS = ROOT / "probes" / "SystemCard3_KoreanFont_current_translation_probe.pce"
OUT_MAP = ROOT / "translation" / "current_translation_probe_char_map.json"
OUT_CONFIG = ROOT / "translation" / "current_translation_probe_bizhawk_config.ini"
OUT_MANIFEST = ROOT / "translation" / "current_translation_probe_manifest.json"
BASE_CONFIG = ROOT / "translation" / "one_glyph_bizhawk_config.ini"

DATA_TRACK_OFFSET = 7_914_480
SOURCE_ISO_OFFSET = 0x010B9E7
EXPECTED_BIN_SHA256 = "d16d29eb80b1b74a2ec929924349256b50b8f9f5c9a3fa37b6fcc08b059b22c5"
EXPECTED_BIOS_SHA1 = "79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c"
FONT_OFFSET = 0x30000
GLYPH_BYTES = 18


def digest(path: Path, algorithm: str = "sha256") -> str:
	h = hashlib.new(algorithm)
	with path.open("rb") as source:
		for chunk in iter(lambda: source.read(1024 * 1024), b""):
			h.update(chunk)
	return h.hexdigest()


def render_glyph(ch: str, font: ImageFont.FreeTypeFont) -> bytes:
	"""Use the exact 12x12/18-byte encoder validated by the one-glyph probe."""
	image = Image.new("1", (12, 12), 0)
	draw = ImageDraw.Draw(image)
	width = font.getmask(ch).size[0]
	draw.text((max(0, (12 - width) // 2), 1), ch, font=font, fill=1)
	pixels = image.load()
	rows: list[int] = []
	for y in range(12):
		row = 0
		for x in range(12):
			if pixels[x, y]:
				row |= 1 << (11 - x)
		rows.append(row)
	out = bytearray()
	for y in range(0, 12, 2):
		row0, row1 = rows[y:y + 2]
		out.extend((row0 >> 4, ((row0 & 0x0F) << 4) | (row1 >> 8), row1 & 0xFF))
	if len(out) != GLYPH_BYTES:
		raise AssertionError("mode-1 glyph encoder returned the wrong size")
	return bytes(out)


def iter_sjis_pairs(data: bytes):
	i = 0
	while i + 1 < len(data):
		if (0x81 <= data[i] <= 0x9F) or (0xE0 <= data[i] <= 0xEF):
			trail = data[i + 1]
			if 0x40 <= trail <= 0xFC and trail != 0x7F:
				yield data[i:i + 2]
				i += 2
				continue
		i += 1


def parse_runs(data: bytes):
	"""Split dialogue bytes into immutable controls and replaceable text runs."""
	runs = []
	i = 0
	start = 0
	while i < len(data):
		control_size = 0
		if data[i] in (0x0C, 0x0D):
			control_size = 1
		elif data[i] in (ord("#"), ord("%")) and i + 1 < len(data):
			control_size = 2
		if control_size:
			if start < i:
				runs.append({"kind": "text", "start": start, "end": i, "data": data[start:i]})
			runs.append({"kind": "control", "start": i, "end": i + control_size,
			             "data": data[i:i + control_size]})
			i += control_size
			start = i
		else:
			i += 1
	if start < len(data):
		runs.append({"kind": "text", "start": start, "end": len(data), "data": data[start:]})
	return runs


def encode_text(text: str, char_map: dict[str, bytes]) -> bytes:
	out = bytearray()
	for ch in text:
		if ch in char_map:
			out.extend(char_map[ch])
		else:
			out.extend(ch.encode("shift_jis"))
	return bytes(out)


def truncate_to_capacity(text: str, capacity: int, char_map: dict[str, bytes]):
	out = bytearray()
	kept = []
	for ch in text:
		encoded = encode_text(ch, char_map)
		if len(out) + len(encoded) > capacity:
			break
		out.extend(encoded)
		kept.append(ch)
	return "".join(kept), bytes(out)


def coalesce_offsets(offsets: list[int]):
	if not offsets:
		return []
	ranges = []
	start = previous = offsets[0]
	for value in offsets[1:]:
		if value != previous + 1:
			ranges.append([start, previous + 1])
			start = value
		previous = value
	ranges.append([start, previous + 1])
	return ranges


def audit_diff(original: Path, patched: Path, allowed: list[tuple[int, int]]):
	if original.stat().st_size != patched.stat().st_size:
		raise AssertionError(f"size changed: {original.name} -> {patched.name}")
	diffs: list[int] = []
	base = 0
	with original.open("rb") as left, patched.open("rb") as right:
		while True:
			a = left.read(1024 * 1024)
			b = right.read(1024 * 1024)
			if not a:
				break
			if a != b:
				for index, (old, new) in enumerate(zip(a, b)):
					if old != new:
						position = base + index
						if not any(start <= position < end for start, end in allowed):
							raise AssertionError(f"undeclared diff at {position:#x}")
						diffs.append(position)
			base += len(a)
	return diffs


def main() -> None:
	if digest(ORIGINAL_BIN) != EXPECTED_BIN_SHA256:
		raise ValueError("unexpected original BIN revision")
	if digest(ORIGINAL_BIOS, "sha1") != EXPECTED_BIOS_SHA1:
		raise ValueError("unexpected System Card 3.0(J) revision")

	with MASTER_CSV.open(encoding="utf-8-sig", newline="") as source:
		rows = list(csv.DictReader(source))
	target = next(row for row in rows if int(row["iso_offset"], 16) == SOURCE_ISO_OFFSET)
	if target["status"] != "verified_corrected_boundary":
		raise ValueError("first-dialogue row lost its corrected-boundary verification")
	source_record = bytes.fromhex(target["raw_hex"])
	if not source_record.endswith(b"\x00") or b"\x00" in source_record[:-1]:
		raise ValueError("master raw_hex must contain exactly one trailing NUL")
	source_bytes = source_record[:-1]

	match = re.fullmatch(
		r"#5(?P<speaker1>.*?)\\n#1(?P<body1>.*?)\\n#5(?P<speaker2>.*?)\\n#1"
		r"(?P<body2>.*?)\\n#5(?P<speaker3>.*?)\\n#1(?P<body3>.*)",
		target["translation"],
	)
	if not match:
		raise ValueError("current first-dialogue translation no longer matches the expected six-run form")
	body_translations = [match.group("body1"), match.group("body2"), match.group("body3")]

	bios_original = ORIGINAL_BIOS.read_bytes()
	protected_indices: set[int] = set()
	for row in rows:
		raw_hex = row.get("raw_hex", "").strip()
		if not raw_hex:
			continue
		try:
			raw = bytes.fromhex(raw_hex)
		except ValueError as exc:
			raise ValueError(f'invalid raw_hex in {row.get("id", "unknown")}') from exc
		for code in iter_sjis_pairs(raw):
			index = glyph_index(code, bios_original)
			if index is not None:
				protected_indices.add(index)

	hangul = list(dict.fromkeys(ch for text in body_translations for ch in text
	                           if "가" <= ch <= "힣"))
	valid: dict[int, bytes] = {}
	for lead in list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)):
		for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
			code = bytes((lead, trail))
			index = glyph_index(code, bios_original)
			if index is not None:
				valid.setdefault(index, code)
	candidates = [(index, code) for index, code in sorted(valid.items(), reverse=True)
	              if index not in protected_indices
	              and FONT_OFFSET + index * GLYPH_BYTES + GLYPH_BYTES <= len(bios_original)]
	if len(candidates) < len(hangul):
		raise ValueError(f"only {len(candidates)} safe slots for {len(hangul)} probe glyphs")
	selected = candidates[:len(hangul)]
	char_map = {ch: code for ch, (_, code) in zip(hangul, selected)}

	# Expected Writes: build and validate every BIOS write before applying any.
	font = ImageFont.truetype(str(FONT_TTF), 11)
	bios_writes = []
	for ch, (index, code) in zip(hangul, selected):
		offset = FONT_OFFSET + index * GLYPH_BYTES
		replacement = render_glyph(ch, font)
		bios_writes.append({
			"owner": f"glyph:{ch}", "offset": offset,
			"expected": bios_original[offset:offset + GLYPH_BYTES], "replacement": replacement,
			"sjis": code, "glyph_index": index,
		})
	for left, right in zip(sorted(bios_writes, key=lambda x: x["offset"]),
	                       sorted(bios_writes, key=lambda x: x["offset"])[1:]):
		if left["offset"] + GLYPH_BYTES > right["offset"]:
			raise AssertionError("overlapping BIOS writes")
	bios_patched = bytearray(bios_original)
	for write in bios_writes:
		start = write["offset"]
		if bytes(bios_patched[start:start + GLYPH_BYTES]) != write["expected"]:
			raise AssertionError(f'BIOS expected-write mismatch for {write["owner"]}')
		bios_patched[start:start + GLYPH_BYTES] = write["replacement"]
	OUT_BIOS.write_bytes(bios_patched)
	bios_diff = audit_diff(ORIGINAL_BIOS, OUT_BIOS,
	                       [(x["offset"], x["offset"] + GLYPH_BYTES) for x in bios_writes])

	# The corrected row starts with #5.  Keep all controls and speaker runs intact.
	runs = parse_runs(source_bytes)
	text_runs = [run for run in runs if run["kind"] == "text"]
	if len(text_runs) != 6:
		raise AssertionError(f"expected six first-dialogue text runs, found {len(text_runs)}")
	body_runs = [text_runs[1], text_runs[3], text_runs[5]]
	game_writes = []
	kept_bodies = []
	for number, (run, translation) in enumerate(zip(body_runs, body_translations), 1):
		capacity = run["end"] - run["start"]
		kept, encoded = truncate_to_capacity(translation, capacity, char_map)
		replacement = encoded + bytes((0x20,)) * (capacity - len(encoded))
		kept_bodies.append(kept)
		game_writes.append({
			"owner": f"first_dialogue_body_{number}",
			"iso_offset": SOURCE_ISO_OFFSET + run["start"],
			"expected": run["data"], "replacement": replacement,
			"translation": translation, "kept_translation": kept,
		})

	physical_source = DATA_TRACK_OFFSET + SOURCE_ISO_OFFSET
	with ORIGINAL_BIN.open("rb") as source:
		source.seek(physical_source)
		if source.read(len(source_record)) != source_record:
			raise AssertionError("corrected master row does not match the original BIN")
	for write in game_writes:
		with ORIGINAL_BIN.open("rb") as source:
			position = DATA_TRACK_OFFSET + write["iso_offset"]
			source.seek(position)
			if source.read(len(write["expected"])) != write["expected"]:
				raise AssertionError(f'game expected-write mismatch for {write["owner"]}')

	shutil.copyfile(ORIGINAL_BIN, OUT_BIN)
	with OUT_BIN.open("r+b") as target_file:
		for write in game_writes:
			position = DATA_TRACK_OFFSET + write["iso_offset"]
			target_file.seek(position)
			target_file.write(write["replacement"])
	allowed_game = [(DATA_TRACK_OFFSET + x["iso_offset"],
	                 DATA_TRACK_OFFSET + x["iso_offset"] + len(x["replacement"]))
	                for x in game_writes]
	game_diff = audit_diff(ORIGINAL_BIN, OUT_BIN, allowed_game)

	cue_text = ORIGINAL_CUE.read_text(encoding="ascii")
	if cue_text.count(ORIGINAL_BIN.name) != 1:
		raise AssertionError("original CUE does not contain exactly one BIN reference")
	OUT_CUE.write_text(cue_text.replace(ORIGINAL_BIN.name, OUT_BIN.name), encoding="ascii")

	map_json = {
		ch: {"sjis": code.hex().upper(), "glyph_index": index,
		     "bios_offset": FONT_OFFSET + index * GLYPH_BYTES}
		for ch, (index, code) in zip(hangul, selected)
	}
	OUT_MAP.write_text(json.dumps(map_json, ensure_ascii=False, indent=2), encoding="utf-8")
	config = BASE_CONFIG.read_text(encoding="utf-8")
	old_bios_json = str(ROOT / "probes" / "SystemCard3_one_glyph_probe.pce").replace("\\", "\\\\")
	new_bios_json = str(OUT_BIOS).replace("\\", "\\\\")
	config = config.replace(old_bios_json, new_bios_json)
	if new_bios_json not in config:
		raise AssertionError("failed to update BizHawk firmware override")
	OUT_CONFIG.write_text(config, encoding="utf-8")

	manifest = {
		"format": "CURRENT-TRANSLATION-MODE1-FIRST-DIALOGUE-PROBE",
		"runtime_status": "PENDING",
		"purpose": "Verify multi-glyph Hangul output using the current master translation.",
		"input": {
			"original_bin_sha256": EXPECTED_BIN_SHA256,
			"original_bios_sha1": EXPECTED_BIOS_SHA1,
			"master_row_id": target["id"], "master_status": target["status"],
			"source_iso_offset": SOURCE_ISO_OFFSET,
		},
		"safety": {
			"font_mode": 1, "font_offset": FONT_OFFSET, "glyph_bytes": GLYPH_BYTES,
			"protected_indices_from_master_raw_hex": len(protected_indices),
			"speaker_runs_changed": 0, "control_bytes_changed": 0,
			"game_expected_writes": len(game_writes),
			"game_diff_bytes": len(game_diff), "bios_expected_writes": len(bios_writes),
			"bios_diff_bytes": len(bios_diff),
		},
		"body_runs": [
			{"iso_offset": x["iso_offset"], "capacity": len(x["expected"]),
			 "translation": x["translation"], "kept_translation": x["kept_translation"],
			 "expected_hex": x["expected"].hex().upper(),
			 "replacement_hex": x["replacement"].hex().upper()}
			for x in game_writes
		],
		"glyphs": map_json,
		"diff_ranges": {
			"game_physical": coalesce_offsets(game_diff),
			"bios": coalesce_offsets(bios_diff),
		},
		"outputs": {
			"bios": str(OUT_BIOS), "bios_sha256": digest(OUT_BIOS),
			"bin": str(OUT_BIN), "bin_sha256": digest(OUT_BIN),
			"cue": str(OUT_CUE), "char_map": str(OUT_MAP),
			"bizhawk_config": str(OUT_CONFIG),
		},
		"pass_criteria": "Game graphics remain normal and the three first-dialogue body runs display readable Hangul.",
		"fail_criteria": "Global graphics corrupt, dialogue flow breaks, or mapped Hangul renders as unrelated glyphs.",
	}
	OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"master row: {target['id']} ({target['status']})")
	print(f"body translations: {body_translations}")
	print(f"kept bodies: {kept_bodies}")
	print(f"Hangul glyphs: {len(hangul)}")
	print(f"BIOS changed bytes: {len(bios_diff)}")
	print(f"game changed bytes: {len(game_diff)}")
	print(f"BIOS: {OUT_BIOS}")
	print(f"CUE: {OUT_CUE}")


if __name__ == "__main__":
	main()
