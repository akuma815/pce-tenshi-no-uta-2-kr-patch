-- Trace the real System Card 3.0(J) source selected by EX_GETFNT.
-- Use only with the original BIOS. The trace pairs the entry SJIS bytes at
-- $F124 with the mapped source pointer immediately before the 32-byte copy at
-- $F1B9, and checks the calculated physical offset against the firmware file.

local output_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ex_getfnt_source_trace.tsv]]
local status_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ex_getfnt_source_trace_status.txt]]
local bios_path = [[H:\BizHawk\Firmware\PCECD_3.0-(J).pce]]

local output = assert(io.open(output_path, "w"))
local bios_file = assert(io.open(bios_path, "rb"))
local bios = assert(bios_file:read("*all"))
bios_file:close()

output:write("frame\tinput_sjis\tfont_mode\tsource_ptr\tpage\tmpr\tphysical_offset\tphysical_match\tsearch_offsets\tdestination\tsource_32\n")
output:flush()

local pending = nil
local records = 0
local cd_reads = 0

local function controller_keys()
	local keys = {}
	for key, _ in pairs(joypad.get(1)) do keys[#keys + 1] = key end
	table.sort(keys)
	return table.concat(keys, ",")
end

local function write_status(label)
	local status = assert(io.open(status_path, "w"))
	status:write(string.format("status=%s\nframe=%d\nsystem=%s\nrom_name=%s\nrom_hash=%s\npc=%04X\nmpr2=%02X\nmpr3=%02X\nmpr4=%02X\nmpr5=%02X\nmpr6=%02X\ncontroller_keys=%s\ncd_reads=%d\ngetfnt_records=%d\n",
		label, emu.framecount(), emu.getsystemid(), gameinfo.getromname(), gameinfo.getromhash(),
		emu.getregister("PC"), emu.getregister("MPR-2"), emu.getregister("MPR-3"),
		emu.getregister("MPR-4"), emu.getregister("MPR-5"), emu.getregister("MPR-6"),
		controller_keys(), cd_reads, records))
	status:close()
end

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_bus_bytes(address, count)
	local values = memory.read_bytes_as_array(address, count, "System Bus")
	local chars = {}
	local hex = {}
	for i = 1, count do
		local value = values[i] or values[i - 1]
		chars[i] = string.char(value)
		hex[i] = string.format("%02X", value)
	end
	return table.concat(chars), table.concat(hex)
end

local function find_offsets(needle, limit)
	local offsets = {}
	local start = 1
	while #offsets < limit do
		local found = string.find(bios, needle, start, true)
		if not found then break end
		offsets[#offsets + 1] = string.format("%05X", found - 1)
		start = found + 1
	end
	return #offsets == 0 and "-" or table.concat(offsets, ",")
end

local function on_entry()
	pending = {
		frame = emu.framecount(),
		lead = read_dp(0xF8),
		trail = read_dp(0xF9),
		mode = read_dp(0xFF)
	}
end

local function on_cd_read()
	cd_reads = cd_reads + 1
end

local function on_copy()
	local source = read_dp(0xEC) + read_dp(0xED) * 0x100
	local destination = read_dp(0xFA) + read_dp(0xFB) * 0x100
	local page = math.floor(source / 0x2000)
	local mpr = emu.getregister("MPR-" .. page)
	local physical = mpr * 0x2000 + (source % 0x2000)
	local source_binary, source_hex = read_bus_bytes(source, 32)
	local expected = bios:sub(physical + 1, physical + 32)
	local matches = expected == source_binary
	local searched = matches and string.format("%05X", physical) or find_offsets(source_binary, 8)
	local input = pending or { frame = emu.framecount(), lead = 0, trail = 0, mode = read_dp(0xFF) }

	output:write(string.format(
		"%d\t%02X%02X\t%02X\t%04X\t%d\t%02X\t%05X\t%s\t%s\t%04X\t%s\n",
		input.frame, input.lead, input.trail, input.mode, source, page, mpr,
		physical, matches and "YES" or "NO", searched, destination, source_hex))
	output:flush()

	records = records + 1
	if records <= 12 or not matches then
		console.log(string.format(
			"EX_GETFNT %02X%02X src=%04X MPR-%d=%02X physical=%05X match=%s search=%s",
			input.lead, input.trail, source, page, mpr, physical,
			matches and "YES" or "NO", searched))
	end
	pending = nil
end

event.on_bus_exec(on_entry, 0xF124, "EX_GETFNT entry", "System Bus")
event.on_bus_exec(on_copy, 0xF1B9, "EX_GETFNT source copy", "System Bus")
event.on_bus_exec(on_cd_read, 0xE009, "EX_GETFNT trace CD heartbeat", "System Bus")
event.onexit(function() output:close() end, "Close EX_GETFNT trace")

console.log("EX_GETFNT source tracer active: " .. output_path)
write_status("started")
while true do
	-- Diagnostic-only navigation: clear the System Card/title waits and advance
	-- dialogue far enough to exercise EX_GETFNT without requiring manual input.
	local frame = emu.framecount()
	local pulse = frame > 300 and frame % 120 < 3
	joypad.set({ ["Run"] = pulse, ["B1"] = pulse, ["B2"] = pulse }, 1)
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
