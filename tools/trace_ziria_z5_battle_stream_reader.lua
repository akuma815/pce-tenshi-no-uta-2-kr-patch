-- Z5 exact battle stream-reader trace.
-- Load manually after the first battle screen is visible.  Read-only: no
-- controller injection and no writes to emulated memory.

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_stream_reader_trace.tsv]]
local status_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_stream_reader_status.txt]]

local output = assert(io.open(output_path, "w"))
output:write("frame\treader\tvalue\tlogical\tpage\tmpr\tphysical\tbattle_module_offset\tptr4b\tptr52\tptr54\tbank_base\toverlay_delta\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\n")
output:flush()

local records = 0

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_word_dp(address)
	return read_dp(address) + read_dp(address + 1) * 0x100
end

local function write_status(label)
	local status = assert(io.open(status_path, "w"))
	status:write(string.format(
		"status=%s\nframe=%d\nrecords=%d\npc=%04X\nmpr2=%02X\nmpr3=%02X\nmpr4=%02X\nmpr5=%02X\nmpr6=%02X\n",
		label, emu.framecount(), records, emu.getregister("PC"),
		emu.getregister("MPR-2"), emu.getregister("MPR-3"), emu.getregister("MPR-4"),
		emu.getregister("MPR-5"), emu.getregister("MPR-6")))
	status:close()
end

local function record(reader, logical)
	local page = math.floor(logical / 0x2000)
	local mpr = emu.getregister("MPR-" .. page)
	local physical = mpr * 0x2000 + (logical % 0x2000)
	local battle_offset = "-"
	if mpr >= 0x68 and mpr <= 0x7F then
		battle_offset = string.format("%05X", (mpr - 0x68) * 0x2000 + (logical % 0x2000))
	end
	local value = memory.read_u8(logical, "System Bus")

	output:write(string.format(
		"%d\t%s\t%02X\t%04X\t%d\t%02X\t%05X\t%s\t%04X\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
		emu.framecount(), reader, value, logical, page, mpr, physical, battle_offset,
		read_word_dp(0x4B), read_word_dp(0x52), read_word_dp(0x54),
		memory.read_u8(0x22D0, "System Bus"), memory.read_u8(0x2E69, "System Bus"),
		emu.getregister("MPR-2"), emu.getregister("MPR-3"), emu.getregister("MPR-4"),
		emu.getregister("MPR-5"), emu.getregister("MPR-6")))
	output:flush()
	records = records + 1

	if records <= 40 then
		console.log(string.format(
			"Z5 STREAM %s value=%02X addr=%04X MPR%d=%02X phys=%05X battle_off=%s",
			reader, value, logical, page, mpr, physical, battle_offset))
	end
end

-- At $4293 the bank-window helper has already installed $22D0+$0C through
-- MPR4-6, so the observed MPR is the exact physical source bank.
event.on_bus_exec(function() record("main", read_word_dp(0x4B)) end,
	0x4293, "Z5 main stream read", "System Bus")

-- $42DE runs after the $2E69 overlay bank has been installed in MPR6.
event.on_bus_exec(function() record("overlay", read_word_dp(0x4B)) end,
	0x42DE, "Z5 overlay stream read", "System Bus")

event.on_bus_exec(function() record("ptr52", read_word_dp(0x52)) end,
	0x42AB, "Z5 pointer-52 stream read", "System Bus")

event.on_bus_exec(function() record("ptr54", read_word_dp(0x54)) end,
	0x42BA, "Z5 pointer-54 stream read", "System Bus")

event.onexit(function()
	write_status("closed")
	output:close()
end, "Close Z5 stream trace")

console.log("Z5 exact battle stream-reader tracer active; no automatic input")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
