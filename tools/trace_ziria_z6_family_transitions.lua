-- Z6 family-transition ownership trace for the runtime-passed Z5 build.
-- Load manually after the first field is visible.  This script is read-only:
-- no joypad injection and no emulated-memory writes.

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z6_family_transition_trace.tsv]]
local status_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z6_family_transition_status.txt]]

local output = assert(io.open(output_path, "w"))
output:write("frame\tevent\tpc\ts\tcall_pc\tcall_page\tcall_mpr\tcode\tfont_mode\tdestination\tlba\tcount\tdest_bank\tcd_mode\tmpr0\tmpr1\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\tmpr7\tdp_hash\tstack_hex\tbank_base\toverlay_delta\ttext_ptr\taux_ptr52\taux_ptr54\tparser_state\n")
output:flush()

local records = 0
local getfnt_records = 0
local cd_records = 0

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_word_dp(address)
	return read_dp(address) + read_dp(address + 1) * 0x100
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

local function dp_hash()
	-- 32-bit rolling hash; multiplier keeps arithmetic exact in Lua doubles.
	local hash = 2166136261
	for i = 0, 0xFF do
		hash = (hash * 65599 + read_dp(i)) % 4294967296
	end
	return string.format("%08X", hash)
end

local function stack_hex()
	local s = emu.getregister("S")
	local values = {}
	for i = 1, 16 do
		values[i] = string.format("%02X", memory.read_u8(0x2100 + ((s + i) % 0x100), "System Bus"))
	end
	return table.concat(values)
end

local function mprs()
	local result = {}
	for i = 0, 7 do result[i + 1] = emu.getregister("MPR-" .. i) end
	return result
end

local function write_status(label)
	local m = mprs()
	local status = assert(io.open(status_path, "w"))
	status:write(string.format(
		"status=%s\nframe=%d\nrecords=%d\ngetfnt_records=%d\ncd_records=%d\npc=%04X\ns=%02X\nmpr=%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X\nrom_name=%s\nrom_hash=%s\n",
		label, emu.framecount(), records, getfnt_records, cd_records,
		emu.getregister("PC"), emu.getregister("S"),
		m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8],
		gameinfo.getromname(), gameinfo.getromhash()))
	status:close()
end

local function record(event_name, extra)
	extra = extra or {}
	local m = mprs()
	output:write(string.format(
		"%d\t%s\t%04X\t%02X\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\t%s\t%02X\t%02X\t%04X\t%04X\t%04X\t%02X\n",
		emu.framecount(), event_name, emu.getregister("PC"), emu.getregister("S"),
		extra.call_pc or "-", extra.call_page or "-", extra.call_mpr or "-",
		extra.code or "-", extra.font_mode or "-", extra.destination or "-",
		extra.lba or "-", extra.count or "-", extra.dest_bank or "-", extra.cd_mode or "-",
		m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8],
		dp_hash(), stack_hex(), memory.read_u8(0x22D0, "System Bus"),
		memory.read_u8(0x2E69, "System Bus"), read_word_dp(0x4B),
		read_word_dp(0x52), read_word_dp(0x54), memory.read_u8(0x2FE3, "System Bus")))
	output:flush()
	records = records + 1
end

local function on_getfnt()
	local s = emu.getregister("S")
	local low = memory.read_u8(0x2100 + ((s + 1) % 0x100), "System Bus")
	local high = memory.read_u8(0x2100 + ((s + 2) % 0x100), "System Bus")
	local return_pc = (low + high * 0x100 + 1) % 0x10000
	local call_pc = (return_pc - 3) % 0x10000
	local page = math.floor(call_pc / 0x2000)
	local call_mpr = emu.getregister("MPR-" .. page)
	record("GETFNT", {
		call_pc = string.format("%04X", call_pc),
		call_page = tostring(page),
		call_mpr = string.format("%02X", call_mpr),
		code = string.format("%02X%02X", read_dp(0xF9), read_dp(0xF8)),
		font_mode = string.format("%02X", read_dp(0xFF)),
		destination = string.format("%04X", read_word_dp(0xFA)),
	})
	getfnt_records = getfnt_records + 1
	if getfnt_records <= 24 then
		console.log(string.format("Z6 GETFNT call=%04X MPR%d=%02X code=%02X%02X",
			call_pc, page, call_mpr, read_dp(0xF9), read_dp(0xF8)))
	end
end

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	record("CD_READ", {
		lba = tostring(lba),
		count = tostring(read_dp(0xF8)),
		dest_bank = string.format("%02X", read_dp(0xFA)),
		cd_mode = string.format("%02X", read_dp(0xFF)),
	})
	cd_records = cd_records + 1
	console.log(string.format("Z6 CD_READ lba=%d count=%d bank=%02X mode=%02X",
		lba, read_dp(0xF8), read_dp(0xFA), read_dp(0xFF)))
end

event.on_bus_exec(on_getfnt, 0xF124, "Z6 EX_GETFNT entry", "System Bus")
event.on_bus_exec(on_cd_read, 0xE009, "Z6 CD_READ entry", "System Bus")
event.onexit(function()
	record("EXIT")
	write_status("closed")
	output:close()
end, "Close Z6 family transition trace")

console.log("Z6 family-transition tracer active; no automatic input")
record("START")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 60 == 0 then
		record("HEARTBEAT")
		write_status("running")
	end
end
