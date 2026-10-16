-- Z6 exact stream-source ownership trace for the runtime-passed Z5 build.
-- Load manually after the first field appears.  Read-only: this script does
-- not inject controller input and never writes to emulated memory.

local root = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]
local output_path = root .. [[ziria_z6_stream_source_trace.tsv]]
local status_path = root .. [[ziria_z6_stream_source_status.txt]]

local output = assert(io.open(output_path, "w"))
output:write("frame\tevent\treader\tvalue\tlogical\tpage\tmpr\tphysical\tfield_module_offset\toverlay_offset\tlast_lba\tiso_offset\tptr4b\tptr52\tptr54\tcode\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\n")
output:flush()

local records = 0
local stream_records = 0
local getfnt_records = 0
local cd_records = 0
local last_lba = -1
local last_count = 0
local last_dest = 0
local last_mode = 0

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_word_dp(address)
	return read_dp(address) + read_dp(address + 1) * 0x100
end

local function mapped(logical)
	local page = math.floor(logical / 0x2000)
	local mpr = emu.getregister("MPR-" .. page)
	local physical = mpr * 0x2000 + (logical % 0x2000)
	local field_offset = "-"
	local overlay_offset = "-"
	local iso_offset = "-"
	if mpr >= 0x80 and mpr <= 0x84 then
		field_offset = string.format("%05X", (mpr - 0x80) * 0x2000 + (logical % 0x2000))
	elseif mpr >= 0x68 and mpr <= 0x7F then
		local offset = (mpr - 0x68) * 0x2000 + (logical % 0x2000)
		overlay_offset = string.format("%05X", offset)
		if last_lba >= 0 and last_mode == 0x06 then
			iso_offset = string.format("%07X", last_lba * 0x800 + offset)
		end
	end
	return page, mpr, physical, field_offset, overlay_offset, iso_offset
end

local function write_status(label)
	local status = assert(io.open(status_path, "w"))
	status:write(string.format(
		"status=%s\nframe=%d\nrecords=%d\nstream_records=%d\ngetfnt_records=%d\ncd_records=%d\nlast_lba=%d\nlast_count=%d\nlast_dest=%02X\nlast_mode=%02X\npc=%04X\nmpr=%02X,%02X,%02X,%02X,%02X\n",
		label, emu.framecount(), records, stream_records, getfnt_records,
		cd_records, last_lba, last_count, last_dest, last_mode,
		emu.getregister("PC"), emu.getregister("MPR-2"),
		emu.getregister("MPR-3"), emu.getregister("MPR-4"),
		emu.getregister("MPR-5"), emu.getregister("MPR-6")))
	status:close()
end

local function record(event_name, reader, logical, value, code)
	local page, mpr, physical, field_offset, overlay_offset, iso_offset =
		mapped(logical)
	output:write(string.format(
		"%d\t%s\t%s\t%s\t%04X\t%d\t%02X\t%05X\t%s\t%s\t%d\t%s\t%04X\t%04X\t%04X\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\n",
		emu.framecount(), event_name, reader or "-", value or "-", logical,
		page, mpr, physical, field_offset, overlay_offset, last_lba,
		iso_offset, read_word_dp(0x4B), read_word_dp(0x52), read_word_dp(0x54),
		code or "-", emu.getregister("MPR-2"), emu.getregister("MPR-3"),
		emu.getregister("MPR-4"), emu.getregister("MPR-5"),
		emu.getregister("MPR-6")))
	output:flush()
	records = records + 1
end

local function record_stream(reader, logical)
	record("STREAM", reader, logical,
		string.format("%02X", memory.read_u8(logical, "System Bus")), "-")
	stream_records = stream_records + 1
	if stream_records <= 32 then
		local page, mpr, physical, field_offset, overlay_offset, iso_offset = mapped(logical)
		console.log(string.format(
			"Z6SRC %s addr=%04X MPR%d=%02X phys=%05X field=%s overlay=%s iso=%s",
			reader, logical, page, mpr, physical, field_offset, overlay_offset, iso_offset))
	end
end

local function on_getfnt()
	local code = string.format("%02X%02X", read_dp(0xF9), read_dp(0xF8))
	record("GETFNT", "-", read_word_dp(0x4B), "-", code)
	getfnt_records = getfnt_records + 1
end

local function on_cd_read()
	last_lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	last_count = read_dp(0xF8)
	last_dest = read_dp(0xFA)
	last_mode = read_dp(0xFF)
	local logical = 0xC000
	record("CD_READ", "-", logical, "-", "-")
	cd_records = cd_records + 1
	console.log(string.format("Z6SRC CD_READ lba=%d count=%d bank=%02X mode=%02X",
		last_lba, last_count, last_dest, last_mode))
end

event.on_bus_exec(function() record_stream("main", read_word_dp(0x4B)) end,
	0x4293, "Z6 source main", "System Bus")
event.on_bus_exec(function() record_stream("overlay", read_word_dp(0x4B)) end,
	0x42DE, "Z6 source overlay", "System Bus")
event.on_bus_exec(function() record_stream("ptr52", read_word_dp(0x52)) end,
	0x42AB, "Z6 source ptr52", "System Bus")
event.on_bus_exec(function() record_stream("ptr54", read_word_dp(0x54)) end,
	0x42BA, "Z6 source ptr54", "System Bus")
event.on_bus_exec(on_getfnt, 0xF124, "Z6 source GETFNT", "System Bus")
event.on_bus_exec(on_cd_read, 0xE009, "Z6 source CD_READ", "System Bus")

event.onexit(function()
	write_status("closed")
	output:close()
end, "Close Z6 source trace")

console.log("Z6 exact source tracer active; no automatic input")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
