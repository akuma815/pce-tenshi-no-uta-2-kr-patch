-- Z5 battle text-source ownership trace.
-- Load manually only after the first battle screen is visible.
-- This script observes the resident text parser at $9628.  It never injects
-- controller input and never writes to emulated memory.

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_text_source_trace.tsv]]
local status_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_text_source_status.txt]]

local output = assert(io.open(output_path, "w"))
output:write("frame\tcode\tparser_caller\ttext_ptr_after\tsource_addr\tsource_page\tsource_mpr\tsource_physical\tbattle_module_offset\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\tsource_hex\n")
output:flush()

local records = 0

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_stack(offset)
	local s = emu.getregister("S")
	return memory.read_u8(0x2100 + ((s + offset) % 0x100), "System Bus")
end

local function bytes_hex(address, count)
	local bytes = memory.read_bytes_as_array(address, count, "System Bus")
	local result = {}
	for i = 1, count do
		local value = bytes[i] or bytes[i - 1] or 0
		result[i] = string.format("%02X", value)
	end
	return table.concat(result)
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

local function on_parser_dispatch()
	-- $92D6 obtains the two-byte character through JSR $4036 twice.  $D6:$D7
	-- points just after those bytes by the time execution reaches $9628.
	local pointer_after = read_dp(0xD6) + read_dp(0xD7) * 0x100
	local source_addr = (pointer_after - 2) % 0x10000
	local source_page = math.floor(source_addr / 0x2000)
	local source_mpr = emu.getregister("MPR-" .. source_page)
	local source_physical = source_mpr * 0x2000 + (source_addr % 0x2000)

	local return_low = read_stack(1)
	local return_high = read_stack(2)
	local return_pc = (return_low + return_high * 0x100 + 1) % 0x10000
	local parser_caller = (return_pc - 3) % 0x10000

	local lead = memory.read_u8(0x2FE0, "System Bus")
	local trail = memory.read_u8(0x2FDF, "System Bus")
	local battle_offset = "-"
	if source_mpr >= 0x68 and source_mpr <= 0x7F then
		battle_offset = string.format("%05X", (source_mpr - 0x68) * 0x2000 + (source_addr % 0x2000))
	end

	output:write(string.format(
		"%d\t%02X%02X\t%04X\t%04X\t%04X\t%d\t%02X\t%05X\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n",
		emu.framecount(), lead, trail, parser_caller, pointer_after, source_addr,
		source_page, source_mpr, source_physical, battle_offset,
		emu.getregister("MPR-2"), emu.getregister("MPR-3"), emu.getregister("MPR-4"),
		emu.getregister("MPR-5"), emu.getregister("MPR-6"), bytes_hex(source_addr, 16)))
	output:flush()
	records = records + 1

	if records <= 32 then
		console.log(string.format(
			"Z5 SOURCE code=%02X%02X caller=%04X src=%04X MPR%d=%02X battle_off=%s",
			lead, trail, parser_caller, source_addr, source_page, source_mpr, battle_offset))
	end
end

event.on_bus_exec(on_parser_dispatch, 0x9628, "Z5 battle text source", "System Bus")
event.onexit(function()
	write_status("closed")
	output:close()
end, "Close Z5 battle source trace")

console.log("Z5 battle text-source tracer active; no automatic input")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
