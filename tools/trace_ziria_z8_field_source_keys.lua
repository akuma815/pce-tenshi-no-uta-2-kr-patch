-- Z8.3 read-only field source-key probe.
--
-- Open this script manually after the first field is visible.  BizHawk Lua
-- loaded during the BIOS screen has previously stalled this title, so the
-- initial scene identity is an explicit field-start assumption.  The next
-- mode-06 CD read replaces that assumption with the observed LBA/count.
--
-- This script writes host log files only.  It never writes emulated memory,
-- injects controller input, loads state, or modifies the disc image.

local root = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]
local lookup_path = root .. [[ziria_z8_field_source_key_lookup.tsv]]
local output_path = root .. [[ziria_z8_field_source_key_runtime_trace.tsv]]
local status_path = root .. [[ziria_z8_field_source_key_runtime_status.txt]]

local FIELD_LBA = 482
local FIELD_COUNT = 96
local SCENE_BANK_FIRST = 0x68
local SCENE_BANK_LAST = 0x7F

local lookup = {}
local lookup_count = 0
do
	local input = assert(io.open(lookup_path, "r"))
	input:read("*l")
	for line in input:lines() do
		local key, id, iso_offset, raw_length =
			line:match("^([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)$")
		assert(key and id and iso_offset and raw_length, "invalid lookup row")
		assert(not lookup[key], "duplicate source key " .. key)
		lookup[key] = {
			id = id,
			iso_offset = iso_offset,
			raw_length = tonumber(raw_length),
		}
		lookup_count = lookup_count + 1
	end
	input:close()
end
assert(lookup_count == 236, "expected 236 field dialogue source keys")

local output = assert(io.open(output_path, "w"))
output:write(
	"frame\tevent\treader\tlogical\tpage\tmpr\tsource_key\tcatalog_id\t"
	.. "catalog_iso_offset\tvalue\tactive_lba\tactive_count\tactive_mode\t"
	.. "scene_identity_source\tmpr2\tmpr3\tmpr4\tmpr5\tmpr6\n")
output:flush()

local records = 0
local scene_stream_records = 0
local start_hits = 0
local unique_start_hits = {}
local out_of_scene_records = 0
local cd_records = 0

-- Manual-load contract: the user opens this after the first field is visible.
local active_lba = FIELD_LBA
local active_count = FIELD_COUNT
local active_mode = 0x06
local scene_identity_source = "manual_field_visible_assumption"

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function read_word_dp(address)
	return read_dp(address) + read_dp(address + 1) * 0x100
end

local function current_mprs()
	return {
		emu.getregister("MPR-2"),
		emu.getregister("MPR-3"),
		emu.getregister("MPR-4"),
		emu.getregister("MPR-5"),
		emu.getregister("MPR-6"),
	}
end

local function write_status(label)
	local status = assert(io.open(status_path, "w"))
	status:write(string.format(
		"status=%s\nframe=%d\nrecords=%d\nscene_stream_records=%d\n"
		.. "start_hits=%d\nunique_start_hits=%d\nout_of_scene_records=%d\n"
		.. "cd_records=%d\nactive_lba=%d\nactive_count=%d\nactive_mode=%02X\n"
		.. "scene_identity_source=%s\nlookup_count=%d\npc=%04X\n",
		label, emu.framecount(), records, scene_stream_records, start_hits,
		(function()
			local count = 0
			for _ in pairs(unique_start_hits) do count = count + 1 end
			return count
		end)(),
		out_of_scene_records, cd_records, active_lba, active_count, active_mode,
		scene_identity_source, lookup_count, emu.getregister("PC")))
	status:close()
end

local function log_record(
	event_name, reader, logical, page, mpr, source_key, catalog_id,
	catalog_iso_offset, value
)
	local m = current_mprs()
	output:write(string.format(
		"%d\t%s\t%s\t%04X\t%d\t%02X\t%s\t%s\t%s\t%02X\t"
		.. "%d\t%d\t%02X\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\n",
		emu.framecount(), event_name, reader or "-", logical or 0,
		page or 0, mpr or 0, source_key or "-", catalog_id or "-",
		catalog_iso_offset or "-", value or 0, active_lba, active_count,
		active_mode, scene_identity_source, m[1], m[2], m[3], m[4], m[5]))
	output:flush()
	records = records + 1
end

local function record_stream(reader, logical)
	local page = math.floor(logical / 0x2000)
	local mpr = emu.getregister("MPR-" .. page)
	local value = memory.read_u8(logical, "System Bus")
	local field_active =
		active_lba == FIELD_LBA and active_count == FIELD_COUNT and active_mode == 0x06
	if field_active and mpr >= SCENE_BANK_FIRST and mpr <= SCENE_BANK_LAST then
		local relative = (mpr - SCENE_BANK_FIRST) * 0x2000 + (logical % 0x2000)
		local key = string.format("%06X", relative)
		local item = lookup[key]
		if item then
			start_hits = start_hits + 1
			unique_start_hits[item.id] = true
			log_record(
				"START_HIT", reader, logical, page, mpr, key, item.id,
				item.iso_offset, value)
			if start_hits <= 32 then
				console.log(string.format(
					"Z8KEY HIT %s key=%s id=%s logical=%04X MPR%d=%02X",
					reader, key, item.id, logical, page, mpr))
			end
		else
			log_record(
				"STREAM_NONSTART", reader, logical, page, mpr, key, "-", "-", value)
		end
		scene_stream_records = scene_stream_records + 1
	else
		out_of_scene_records = out_of_scene_records + 1
		if out_of_scene_records <= 64 then
			log_record(
				"STREAM_OUTSIDE_FIELD_SCENE", reader, logical, page, mpr,
				"-", "-", "-", value)
		end
	end
end

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	local count = read_dp(0xF8)
	local mode = read_dp(0xFF)
	if mode == 0x06 then
		active_lba = lba
		active_count = count
		active_mode = mode
		scene_identity_source = "observed_mode06_cd_read"
	end
	cd_records = cd_records + 1
	log_record("CD_READ", "-", 0, 0, 0, "-", "-", "-", 0)
	console.log(string.format(
		"Z8KEY CD_READ lba=%d count=%d mode=%02X", lba, count, mode))
end

event.on_bus_exec(
	function() record_stream("main", read_word_dp(0x4B)) end,
	0x4293, "Z8 key main", "System Bus")
event.on_bus_exec(
	function() record_stream("overlay", read_word_dp(0x4B)) end,
	0x42DE, "Z8 key overlay", "System Bus")
event.on_bus_exec(
	function() record_stream("ptr52", read_word_dp(0x52)) end,
	0x42AB, "Z8 key ptr52", "System Bus")
event.on_bus_exec(
	function() record_stream("ptr54", read_word_dp(0x54)) end,
	0x42BA, "Z8 key ptr54", "System Bus")
event.on_bus_exec(on_cd_read, 0xE009, "Z8 key CD_READ", "System Bus")

event.onexit(function()
	write_status("closed")
	output:close()
end, "Close Z8 field source-key probe")

console.log("Z8 field source-key probe active; read-only, manual field-visible start")
write_status("started")

while true do
	emu.frameadvance()
	if emu.framecount() % 120 == 0 then write_status("running") end
end
