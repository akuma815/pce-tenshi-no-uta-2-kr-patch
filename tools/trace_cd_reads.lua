-- Runtime trace for PC Engine BIOS CD_READ ($E009).
-- Launch with: EmuHawk.exe --lua trace_cd_reads.lua game.cue

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\cd_read_trace.tsv]]
local output = assert(io.open(output_path, "w"))
output:write("frame\tlba\tcount\tend\tdest_bank\tmode\ttarget535\n")
output:flush()

local function read8(address)
	-- HuC6280 direct-page $00..$FF is the Work RAM window at System Bus $2000..$20FF.
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function trace_cd_read()
	local lba = read8(0xFC) * 0x10000 + read8(0xFD) * 0x100 + read8(0xFE)
	local count = read8(0xF8)
	local dest = read8(0xFA)
	local mode = read8(0xFF)
	local target = lba <= 535 and 535 < lba + count
	local line = string.format("%d\t%d\t%d\t%d\t%02X\t%02X\t%s\n",
		emu.framecount(), lba, count, lba + count, dest, mode, target and "TARGET" or "")
	output:write(line)
	output:flush()
	if target then
		console.log("CD_READ TARGET535: " .. line)
	end
end

event.on_bus_exec(trace_cd_read, 0xE009, "Trace BIOS CD_READ", "System Bus")
event.onexit(function() output:close() end, "Close CD trace")

console.log("CD_READ tracer active: " .. output_path)
while true do
	emu.frameadvance()
end
