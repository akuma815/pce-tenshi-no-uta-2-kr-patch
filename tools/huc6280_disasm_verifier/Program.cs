using System.Text.Json;
using BizHawk.Emulation.Cores.Components.H6280;

if (args.Length == 5 && args[0] == "--raw")
{
	var path = args[1];
	var rawOrigin = Convert.ToUInt16(args[2], 16);
	var fileOffset = Convert.ToInt32(args[3], 16);
	var length = Convert.ToInt32(args[4], 16);
	var image = File.ReadAllBytes(path);
	if (fileOffset < 0 || length <= 0 || fileOffset + length > image.Length)
	{
		throw new ArgumentOutOfRangeException(nameof(args), "raw range is outside the input file");
	}
	var code = image.AsSpan(fileOffset, length).ToArray();
	var rawCpu = new HuC6280();
	rawCpu.Load(rawOrigin, code);
	var rawPc = rawOrigin;
	var rawEnd = rawOrigin + code.Length;
	while (rawPc < rawEnd)
	{
		var text = rawCpu.Disassemble(rawPc, out var instructionLength);
		if (instructionLength <= 0 || rawPc + instructionLength > rawEnd)
		{
			throw new InvalidDataException($"invalid instruction boundary at {rawPc:X4}: {text}");
		}
		Console.WriteLine($"{rawPc:X4}: {text}");
		rawPc = (ushort) (rawPc + instructionLength);
	}
	return 0;
}

if (args.Length != 1)
{
	Console.Error.WriteLine("usage: huc6280_disasm_verifier <task7 manifest>");
	Console.Error.WriteLine("   or: huc6280_disasm_verifier --raw <file> <origin-hex> <offset-hex> <length-hex>");
	return 2;
}

using var doc = JsonDocument.Parse(File.ReadAllText(args[0]));
var hook = Convert.FromHexString(doc.RootElement.GetProperty("hook").GetProperty("hex").GetString()!);
var originText = doc.RootElement.GetProperty("hook").GetProperty("runtime_address").GetString()!;
var origin = Convert.ToUInt16(originText[2..], 16);
var end = origin + hook.Length;
var cpu = new HuC6280();
cpu.Load(origin, hook);

var pc = origin;
var instructions = 0;
while (pc < end)
{
	var text = cpu.Disassemble(pc, out var length);
	if (length <= 0 || pc + length > end)
	{
		throw new InvalidDataException($"invalid instruction boundary at {pc:X4}: {text}");
	}
	Console.WriteLine($"{pc:X4}: {text}");
	pc = (ushort) (pc + length);
	instructions++;
}

if (pc != end)
{
	throw new InvalidDataException($"disassembly ended at {pc:X4}, expected {end:X4}");
}

// Every relative branch used by this generated image must remain inside the
// hook. Absolute JSR targets are likewise internal; the one external absolute
// transfer is the reviewed fallback JMP $F124.
var relativeOpcodes = new HashSet<byte> { 0x10, 0x30, 0x50, 0x70, 0x80, 0x90, 0xB0, 0xD0, 0xF0 };
pc = origin;
while (pc < end)
{
	var opcode = hook[pc - origin];
	cpu.Disassemble(pc, out var length);
	if (relativeOpcodes.Contains(opcode))
	{
		var delta = unchecked((sbyte) hook[pc - origin + 1]);
		var target = pc + length + delta;
		if (target < origin || target >= end) throw new InvalidDataException($"branch {pc:X4} -> {target:X4} escapes hook");
	}
	if (opcode == 0x20)
	{
		var target = hook[pc - origin + 1] | (hook[pc - origin + 2] << 8);
		if (target < origin || target >= end) throw new InvalidDataException($"JSR {pc:X4} -> {target:X4} escapes hook");
	}
	if (opcode == 0x4C)
	{
		var target = hook[pc - origin + 1] | (hook[pc - origin + 2] << 8);
		if (target != 0xF124) throw new InvalidDataException($"unexpected external JMP {pc:X4} -> {target:X4}");
	}
	pc = (ushort) (pc + length);
}

Console.WriteLine($"PASS: {hook.Length} bytes, {instructions} instructions, exact end {end:X4}");
return 0;
