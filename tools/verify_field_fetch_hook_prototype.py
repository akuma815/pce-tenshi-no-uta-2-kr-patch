#!/usr/bin/env python3
"""Independent structural verifier for the dry-run HuC6280 fetch hook prototype."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "translation" / "field_fetch_hook_prototype.json"
TRAMP = ROOT / "translation" / "field_fetch_trampoline.bin"
HOOK = ROOT / "translation" / "field_fetch_hook.bin"

# Lengths of every opcode emitted by build_field_fetch_hook_prototype.py.
LENGTHS = {
	0x08: 1, 0x09: 2, 0x0A: 1, 0x18: 1, 0x20: 3, 0x28: 1, 0x29: 2,
	0x38: 1, 0x43: 2, 0x48: 1, 0x4C: 3, 0x53: 2, 0x60: 1, 0x64: 2,
	0x68: 1, 0x69: 2, 0x6D: 3, 0x78: 1, 0x80: 2, 0x85: 2, 0x8D: 3,
	0x90: 2, 0x9C: 3, 0xA5: 2, 0xA9: 2, 0xAA: 1, 0xAD: 3, 0xB0: 2,
	0xB2: 2, 0xBD: 3, 0xC9: 2, 0xD0: 2, 0xDA: 1, 0xE6: 2, 0xE8: 1,
	0xE9: 2, 0xEA: 1, 0xEE: 3, 0xF0: 2, 0xFA: 1,
}
RELATIVE = {0x80, 0x90, 0xB0, 0xD0, 0xF0}


def signed(value): return value - 256 if value >= 128 else value


def main():
	m = json.loads(MANIFEST.read_text(encoding="utf-8"))
	assert m["dry_run_only"] is True
	tramp = TRAMP.read_bytes()
	hook = HOOK.read_bytes()
	assert tramp.hex() == m["trampoline"]["image_hex"]
	assert hook.hex() == m["hook"]["hex"]
	assert tramp[:13] == bytes.fromhex("0878da432048a98353204c39a3")
	assert set(tramp[13:]) == {0xEA}

	origin = int(m["hook"]["logical_address"], 16)
	labels = {k: int(v, 16) for k, v in m["labels"].items()}
	code_end = labels["token_table"]
	pc = origin
	boundaries = set()
	control_targets = []
	while pc < code_end:
		boundaries.add(pc)
		op = hook[pc - origin]
		assert op in LENGTHS, f"unknown emitted opcode {op:02X} at {pc:04X}"
		length = LENGTHS[op]
		assert pc + length <= code_end
		if op in RELATIVE:
			target = pc + 2 + signed(hook[pc - origin + 1])
			control_targets.append((pc, target, "relative"))
		elif op in (0x20, 0x4C):
			target = hook[pc - origin + 1] | hook[pc - origin + 2] << 8
			control_targets.append((pc, target, "absolute"))
		pc += length
	assert pc == code_end
	for source, target, kind in control_targets:
		assert target in boundaries, f"{kind} target {target:04X} from {source:04X} is not an instruction"

	# Only internal subroutines may RTS directly; top-level paths jump to this guarded epilogue.
	exit_addr = labels["exit"]
	exit_off = exit_addr - origin
	assert hook[exit_off:exit_off + 12] == bytes.fromhex("8ddf31685320fa28addf3160")
	for name in ("native_rts", "native_main", "translated_raw"):
		assert labels[name] in boundaries
	assert labels["token_table_plus_1"] == labels["token_table"] + 1
	assert labels["active"] == labels["token_table"] + m["token_table_bytes"]
	assert len(hook) < m["hook"]["cave_bytes"]

	print("hook code bytes:", code_end - origin)
	print("control transfers verified:", len(control_targets))
	print("common MPR5/X/P epilogue: OK")
	print("prototype verification: OK (ISO untouched)")


if __name__ == "__main__":
	main()
