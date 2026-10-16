-- 씬 "초기화 구간" read/write coverage probe (Z8.9b 도구의 씬 일반화판).
--
-- 배경(2026-08-24 b8.2 FAIL): play-CDL 은 씬 로드 직후 초기화 read
-- (그래픽 → VRAM 업로드)를 못 본다. 578 의 $6A/$6B 를 play-CDL cold 만으로
-- 채택했다가 새 마을 그래픽 전면 깨짐 — 482 때(2026-07-27 canary FAIL)와
-- 동일 원인. 신규 씬 뱅크 승인은 play-CDL + 이 init coverage 합집합 필수.
--
-- 사용: PCEHawk(원본 cue + cfg_pcehawk_diag.ini), ★타이틀 화면에서★ 로드.
--   대상 씬에 들어가는 순간부터 WINDOW_FRAMES 동안 자동 기록(느려짐).
--   나갔다 재진입으로 창을 2회 이상 확보 → EmuHawk 정상 종료 시 저장.
-- 출력: translation/scene_init_coverage_<LBA>.tsv

local SCENE_LBA = 578          -- ★ 대상 씬
local SCENE_COUNT = 78         -- ★ 그 씬의 섹터 수 (씬 디렉터리 실측)

local root = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]
local out_path = root .. string.format("scene_init_coverage_%d.tsv", SCENE_LBA)

local LOADER_RETURN_PC = 0x66FF
local SCENE_BANK_FIRST = 0x68
local SCENE_BANK_LAST = 0x7F
local SCENE_BYTES = 0x30000
local WINDOW_FRAMES = 240

local touched = {}
for i = 0, SCENE_BYTES - 1 do touched[i] = false end
local MPR_NAME = {}
for page = 0, 7 do MPR_NAME[page] = "MPR-" .. page end

local pending = false
local want_record = false
local recording = false
local window_end = 0
local windows_done = 0
local access_events = 0
local read_id, write_id = nil, nil
local floor = math.floor

local function read_dp(a) return memory.read_u8(0x2000 + a, "System Bus") end

local function on_access(address)
	local page = floor(address / 0x2000)
	local mpr = emu.getregister(MPR_NAME[page])
	if mpr < SCENE_BANK_FIRST or mpr > SCENE_BANK_LAST then return end
	touched[(mpr - SCENE_BANK_FIRST) * 0x2000 + (address % 0x2000)] = true
	access_events = access_events + 1
end

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	local count = read_dp(0xF8)
	local mode = read_dp(0xFF)
	if mode == 0x06 then
		pending = (lba == SCENE_LBA and count == SCENE_COUNT)
		if recording then window_end = 0 end
		console.log(string.format("[init%d] MODE06 lba=%d cnt=%d pending=%s",
			SCENE_LBA, lba, count, tostring(pending)))
	end
end

local function on_loader_return()
	if pending then pending = false; want_record = true end
end

event.on_bus_exec(on_cd_read, 0xE009, "init CD_READ", "System Bus")
event.on_bus_exec(on_loader_return, LOADER_RETURN_PC, "init loader ret", "System Bus")

local function emit()
	local out = assert(io.open(out_path, "w"))
	out:write("format\tZIRIA-SCENE-INIT-COVERAGE-V1\n")
	out:write(string.format("scene_lba\t%d\n", SCENE_LBA))
	out:write(string.format("scene_count\t%d\n", SCENE_COUNT))
	out:write(string.format("window_frames\t%d\n", WINDOW_FRAMES))
	out:write(string.format("windows_done\t%d\n", windows_done))
	out:write(string.format("access_events\t%d\n", access_events))
	out:write(string.format("frame\t%d\n", emu.framecount()))
	out:write("offset\tflags256\n")
	local parts = {}
	local total = 0
	for block = 0, SCENE_BYTES / 256 - 1 do
		local base = block * 256
		for j = 0, 255 do
			if touched[base + j] then
				parts[j + 1] = "x"; total = total + 1
			else
				parts[j + 1] = "."
			end
		end
		out:write(string.format("%06X\t%s\n", base, table.concat(parts)))
	end
	out:close()
	console.log(string.format("[init%d] report: windows=%d touched=%d",
		SCENE_LBA, windows_done, total))
end

event.onexit(emit, "Write scene init coverage")

console.log(string.format("씬 %d init coverage probe 시작 (평상시 무감속).", SCENE_LBA))

while true do
	if want_record and not recording then
		want_record = false
		recording = true
		window_end = emu.framecount() + WINDOW_FRAMES
		read_id = event.on_bus_read(on_access, nil, "init reads", "System Bus")
		write_id = event.on_bus_write(on_access, nil, "init writes", "System Bus")
		console.log(string.format("[init%d] RECORDING start (느려짐)", SCENE_LBA))
	end
	if recording and emu.framecount() >= window_end then
		recording = false
		event.unregisterbyid(read_id)
		event.unregisterbyid(write_id)
		windows_done = windows_done + 1
		emit()
		console.log(string.format("[init%d] window #%d done (정상 속도)",
			SCENE_LBA, windows_done))
	end
	if recording then
		gui.text(8, 8, string.format(
			"INIT RECORDING #%d ... %d frames left - 대기",
			windows_done + 1, window_end - emu.framecount()), "yellow")
	else
		gui.text(8, 8, string.format("scene %d init probe idle (windows=%d)",
			SCENE_LBA, windows_done), "lime")
	end
	emu.frameadvance()
end
