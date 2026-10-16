#!/usr/bin/env python3
"""Assemble the dry-run HuC6280 field fetch trampoline and resident hook."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
PLAN = ROOT / "translation" / "area_patch_plan_materialized.json"
OUT_DIR = ROOT / "translation"
DATA_TRACK_OFFSET = 7_914_480
TRAMP_ISO = 0x41111
TRAMP_ADDR = 0x4111
TRAMP_SIZE = 0x415A - 0x4111
HOOK_ISO = 0x47339
HOOK_ADDR = 0xA339
CAVE_SIZE = 7367


class Assembler:
	def __init__(self, origin):
		self.origin = origin
		self.code = bytearray()
		self.labels = {}
		self.fixups = []

	@property
	def pc(self): return self.origin + len(self.code)

	def label(self, name):
		assert name not in self.labels
		self.labels[name] = self.pc

	def b(self, *values): self.code.extend(values)

	def abs(self, opcode, target):
		self.b(opcode, target & 0xFF, target >> 8)

	def abs_label(self, opcode, label):
		self.b(opcode, 0, 0)
		self.fixups.append((len(self.code) - 2, "abs", label))

	def rel(self, opcode, label):
		self.b(opcode, 0)
		self.fixups.append((len(self.code) - 1, "rel", label))

	def finish(self):
		for offset, kind, label in self.fixups:
			target = self.labels[label]
			if kind == "abs":
				self.code[offset] = target & 0xFF
				self.code[offset + 1] = target >> 8
			else:
				base = self.origin + offset + 1
				delta = target - base
				assert -128 <= delta <= 127, (label, delta)
				self.code[offset] = delta & 0xFF
		return bytes(self.code)


def zp_load(a, zp): a.b(0xA5, zp)
def zp_store(a, zp): a.b(0x85, zp)
def zp_stz(a, zp): a.b(0x64, zp)
def abs_load(a, addr): a.abs(0xAD, addr)
def abs_store(a, addr): a.abs(0x8D, addr)
def abs_stz(a, addr): a.abs(0x9C, addr)


def build():
	plan = json.loads(PLAN.read_text(encoding="utf-8"))
	grid15 = next(x for x in plan["area_writes"] if x["physical_grid"] == 15)
	dictionary = {int(k, 16): bytes.fromhex(v) for k, v in grid15["token_dictionary"].items()}
	expected_tokens = list(range(0x03, 0x0B)) + list(range(0x0F, 0x20))
	assert sorted(dictionary) == expected_tokens
	token_table = b"".join(dictionary[x] for x in expected_tokens)

	# Trampoline preserves flags, X, and the actual previous MPR5 mapping.
	tramp = bytes((
		0x08,                   # PHP
		0x78,                   # SEI
		0xDA,                   # PHX
		0x43, 0x20,             # TMA #$20
		0x48,                   # PHA
		0xA9, 0x83,             # LDA #$83
		0x53, 0x20,             # TAM #$20
		0x4C, HOOK_ADDR & 0xFF, HOOK_ADDR >> 8,  # JMP hook
	))
	assert len(tramp) == 13 and len(tramp) <= TRAMP_SIZE
	tramp_image = tramp + bytes((0xEA,)) * (TRAMP_SIZE - len(tramp))

	a = Assembler(HOOK_ADDR)
	# Absolute module-local state labels are appended after code/data.
	def lda_state(name): a.abs_label(0xAD, name)
	def sta_state(name): a.abs_label(0x8D, name)
	def stz_state(name): a.abs_label(0x9C, name)

	# Pending second byte from a token.
	lda_state("pending_valid"); a.rel(0xF0, "no_pending")
	stz_state("pending_valid"); lda_state("pending_byte"); a.abs_label(0x4C, "exit")

	a.label("no_pending")
	lda_state("active"); a.rel(0xD0, "translated_loop")
	a.abs_label(0x20, "native_fetch")
	a.b(0xC9, 0x01); a.rel(0xF0, "redirect")
	a.abs_label(0x4C, "exit")
	# Redirect header: bank/flags, low, high. Trailing NUL stays in main stream.
	a.label("redirect")
	a.abs_label(0x20, "native_fetch"); a.b(0x48, 0x29, 0x80); sta_state("token_mode")
	a.b(0x68, 0x29, 0x7F); sta_state("stream_bank")
	a.abs_label(0x20, "native_fetch"); sta_state("stream_low")
	a.abs_label(0x20, "native_fetch"); sta_state("stream_high")
	a.b(0xA9, 0x01); sta_state("active")

	a.label("translated_loop")
	a.abs_label(0x20, "translated_raw")
	a.rel(0xF0, "translated_end")
	a.b(0xC9, 0x02); a.rel(0xD0, "token_check")
	a.abs_label(0x20, "translated_raw"); sta_state("stream_bank")
	a.abs_label(0x20, "translated_raw"); sta_state("stream_low")
	a.abs_label(0x20, "translated_raw"); sta_state("stream_high")
	a.rel(0x80, "translated_loop")

	a.label("translated_end")
	stz_state("active"); a.b(0xA9, 0x00); a.abs_label(0x4C, "exit")

	a.label("token_check")
	sta_state("return_byte")
	lda_state("token_mode"); a.rel(0xF0, "return_saved")
	lda_state("return_byte")
	a.b(0xC9, 0x03); a.rel(0x90, "return_saved")
	a.b(0xC9, 0x0B); a.rel(0x90, "token_low")
	a.b(0xC9, 0x0F); a.rel(0x90, "return_saved")
	a.b(0xC9, 0x20); a.rel(0xB0, "return_saved")
	a.b(0x38, 0xE9, 0x07); a.rel(0x80, "token_index")
	a.label("token_low"); a.b(0x38, 0xE9, 0x03)
	a.label("token_index"); a.b(0x0A, 0xAA)  # ASL A / TAX
	a.abs_label(0xBD, "token_table_plus_1"); sta_state("pending_byte")
	a.b(0xA9, 0x01); sta_state("pending_valid")
	a.abs_label(0xBD, "token_table"); a.abs_label(0x4C, "exit")
	a.label("return_saved"); lda_state("return_byte"); a.abs_label(0x4C, "exit")

	# Original priority 1: variable buffer $57/$58; NUL releases and resumes.
	a.label("native_fetch")
	zp_load(a, 0x58); a.rel(0xF0, "native_aux")
	a.b(0xB2, 0x57); a.rel(0xF0, "variable_end")
	a.b(0xE6, 0x57); a.rel(0xD0, "native_rts"); a.b(0xE6, 0x58)
	a.label("native_rts"); a.b(0x60)
	a.label("variable_end"); zp_stz(a, 0x57); zp_stz(a, 0x58); a.rel(0x80, "native_fetch")

	# Original priority 2: native auxiliary stream $55/$56.
	a.label("native_aux")
	zp_load(a, 0x56); a.rel(0xF0, "native_main")
	a.b(0xB2, 0x55, 0xE6, 0x55); a.rel(0xD0, "native_rts"); a.b(0xE6, 0x56, 0x60)

	# Original main stream: map only its current 8 KiB page into MPR3.
	a.label("native_main")
	zp_load(a, 0xFC); a.b(0x48); zp_load(a, 0xFD); a.b(0x48, 0x43, 0x08, 0x48)
	zp_load(a, 0x54); a.b(0xC9, 0xA0); a.rel(0x90, "main_bank0")
	a.b(0xC9, 0xC0); a.rel(0x90, "main_bank1")
	abs_load(a, 0x22D0); a.b(0x18, 0x69, 0x0E); a.rel(0x80, "main_map")
	a.label("main_bank1"); abs_load(a, 0x22D0); a.b(0x18, 0x69, 0x0D); a.rel(0x80, "main_map")
	a.label("main_bank0"); abs_load(a, 0x22D0); a.b(0x18, 0x69, 0x0C)
	a.label("main_map"); a.b(0x53, 0x08)
	zp_load(a, 0x53); zp_store(a, 0xFC); zp_load(a, 0x54); a.b(0x29, 0x1F, 0x09, 0x60); zp_store(a, 0xFD)
	a.b(0xB2, 0xFC); abs_store(a, 0x31DF)
	a.b(0xE6, 0x53); a.rel(0xD0, "main_restore"); a.b(0xE6, 0x54)
	a.label("main_restore"); a.b(0x68, 0x53, 0x08, 0x68); zp_store(a, 0xFD); a.b(0x68); zp_store(a, 0xFC)
	abs_load(a, 0x31DF); a.b(0x60)

	# Mapped translated stream read using module-local pointer state.
	a.label("translated_raw")
	zp_load(a, 0xFC); a.b(0x48); zp_load(a, 0xFD); a.b(0x48, 0x43, 0x08, 0x48)
	abs_load(a, 0x22D0); a.b(0x18); a.abs_label(0x6D, "stream_bank"); a.b(0x53, 0x08)
	lda_state("stream_low"); zp_store(a, 0xFC); lda_state("stream_high"); zp_store(a, 0xFD)
	a.b(0xB2, 0xFC); abs_store(a, 0x31DF)
	a.abs_label(0xEE, "stream_low"); a.rel(0xD0, "translated_restore"); a.abs_label(0xEE, "stream_high")
	a.label("translated_restore"); a.b(0x68, 0x53, 0x08, 0x68); zp_store(a, 0xFD); a.b(0x68); zp_store(a, 0xFC)
	abs_load(a, 0x31DF); a.b(0x60)

	# Common exit restores actual MPR5, X, and flags saved by the trampoline.
	a.label("exit")
	abs_store(a, 0x31DF); a.b(0x68, 0x53, 0x20, 0xFA, 0x28); abs_load(a, 0x31DF); a.b(0x60)

	a.label("token_table"); a.code.extend(token_table)
	# Alias used by absolute-indexed lookup.
	a.labels["token_table_plus_1"] = a.labels["token_table"] + 1
	for name in ("active", "stream_bank", "stream_low", "stream_high", "token_mode",
	             "pending_valid", "pending_byte", "return_byte"):
		a.label(name); a.b(0x00)

	hook = a.finish()
	assert len(hook) <= CAVE_SIZE
	return tramp, tramp_image, hook, a.labels, token_table


def main():
	tramp, tramp_image, hook, labels, token_table = build()
	with BIN.open("rb") as source:
		source.seek(DATA_TRACK_OFFSET + TRAMP_ISO)
		original_fetch = source.read(TRAMP_SIZE)
		source.seek(DATA_TRACK_OFFSET + HOOK_ISO)
		cave = source.read(len(hook))
	assert len(original_fetch) == TRAMP_SIZE
	assert cave == bytes((0xFF,)) * len(hook)

	(OUT_DIR / "field_fetch_trampoline.bin").write_bytes(tramp_image)
	(OUT_DIR / "field_fetch_hook.bin").write_bytes(hook)
	manifest = {
		"format": "FIELD-FETCH-HOOK-PROTOTYPE",
		"version": 1,
		"dry_run_only": True,
		"trampoline": {
			"logical_address": f"0x{TRAMP_ADDR:04X}", "iso_offset": f"0x{TRAMP_ISO:X}",
			"code_bytes": len(tramp), "replaced_bytes": TRAMP_SIZE,
			"original_hex": original_fetch.hex(), "image_hex": tramp_image.hex(),
		},
		"hook": {
			"physical_bank": "0x83", "logical_address": f"0x{HOOK_ADDR:04X}",
			"iso_offset": f"0x{HOOK_ISO:X}", "bytes": len(hook),
			"cave_bytes": CAVE_SIZE, "hex": hook.hex(),
		},
		"labels": {k: f"0x{v:04X}" for k, v in labels.items()},
		"token_table_bytes": len(token_table),
		"guards": ["original fetch signature", "hook cave remains FF", "all relative branches in range"],
	}
	(OUT_DIR / "field_fetch_hook_prototype.json").write_text(
		json.dumps(manifest, indent=2), encoding="utf-8")
	print("trampoline code/image:", len(tramp), "/", len(tramp_image), "bytes")
	print("hook:", len(hook), "/", CAVE_SIZE, "bytes")
	print("token table:", len(token_table), "bytes")
	print("prototype assembly: OK (dry run, ISO untouched)")


if __name__ == "__main__":
	main()
