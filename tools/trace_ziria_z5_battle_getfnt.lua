-- Z5 battle renderer discovery trace.
-- Start this manually only after the first battle screen is visible.
-- It never injects controller input and does not alter emulated memory.

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_getfnt_trace.tsv]]
local status_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z5_battle_getfnt_status.txt]]

local output = assert(io.open(output_path, "w"))
output:write("frame\tcode\tmode\tdestination\treturn_pc\tcall_pc\tcall_page\tcall_mpr\tphysical\tbattle_module_offset\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\tcontext_hex\n")
output:flush()

local records = 0

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_stack(offset)
	local s = emu.getregister("S")
	return memory.read_u8(0x2100 + ((s + offset) % 0x100), "System Bus")
end

local function context_hex(address, count)
	local start = (address - math.floor(count / 2)) % 0x10000
	local bytes = memory.read_bytes_as_array(start, count, "System Bus")
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

local function on_getfnt()
	local return_low = read_stack(1)
	local return_high = read_stack(2)
	local return_pc = (return_low + return_high * 0x100 + 1) % 0x10000
	local call_pc = (return_pc - 3) % 0x10000
	local page = math.floor(call_pc / 0x2000)
	local mpr = emu.getregister("MPR-" .. page)
	local physical = mpr * 0x2000 + (call_pc % 0x2000)
	local battle_offset = "-"
	if mpr >= 0x68 and mpr <= 0x7F then
		battle_offset = string.format("%05X", (mpr - 0x68) * 0x2000 + (call_pc % 0x2000))
	end

	local lead = read_dp(0xF9)
	local trail = read_dp(0xF8)
	local mode = read_dp(0xFF)
	local destination = read_dp(0xFA) + read_dp(0xFB) * 0x100
	local mpr2 = emu.getregister("MPR-2")
	local mpr3 = emu.getregister("MPR-3")
	local mpr4 = emu.getregister("MPR-4")
	local mpr5 = emu.getregister("MPR-5")
	local mpr6 = emu.getregister("MPR-6")

	output:write(string.format(
		"%d\t%02X%02X\t%02X\t%04X\t%04X\t%04X\t%d\t%02X\t%05X\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n",
		emu.framecount(), lead, trail, mode, destination, return_pc, call_pc, page, mpr,
		physical, battle_offset, mpr2, mpr3, mpr4, mpr5, mpr6, context_hex(call_pc, 32)))
	output:flush()
	records = records + 1

	if records <= 24 then
		console.log(string.format(
			"Z5 GETFNT code=%02X%02X call=%04X MPR%d=%02X battle_off=%s",
			lead, trail, call_pc, page, mpr, battle_offset))
	end
end

event.on_bus_exec(on_getfnt, 0xF124, "Z5 battle EX_GETFNT entry", "System Bus")
event.onexit(function()
	write_status("closed")
	output:close()
end, "Close Z5 battle trace")

console.log("Z5 battle GETFNT tracer active; no automatic input")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
