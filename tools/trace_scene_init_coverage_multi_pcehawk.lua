-- 씬 init coverage probe — 다중 씬 자동판 (2026-08-24).
-- 어떤 씬이든 mode-06 씬 로드가 로더 복귀점에 도달하면 WINDOW_FRAMES 동안
-- 자동 기록하고, 씬 LBA 별로 translation/scene_init_coverage_<LBA>.tsv 를
-- 만든다 (창 완료 시마다 저장 — 크래시에도 완료분은 보존).
-- CDL(Code Data Logger)과 같은 세션에서 병행 사용 가능: 이 probe 는 로드
-- 직후 수 초만 느려지고 평상시 무감속이다.
--
-- 사용: PCEHawk(원본 cue + cfg_pcehawk_diag.ini), ★타이틀 화면에서★ 로드.
-- 새 지역 진입마다: (자동) init 기록 → CDL File>New → Save As seg_<LBA>_full.cdl
-- → 콘텐츠 플레이 → 떠나기 전 CDL File>Save.
-- 같은 씬 재진입 시 init 기록이 누적된다 (창 2회 이상 권장).

local root = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]

-- overlay 씬 디렉터리 (lba -> 섹터수, ziria_module_catalog 실측)
local SCENES = {
  [290]=96, [386]=96, [482]=96, [578]=78, [674]=96, [770]=96, [866]=96,
  [962]=96, [1058]=83, [1154]=96, [1250]=96, [1346]=96, [1442]=96,
  [1538]=73, [1634]=96, [1730]=92, [1826]=96, [1922]=96, [2018]=82,
  [2114]=75, [2210]=76, [2306]=96, [2402]=96, [2498]=71, [2594]=71,
  [2690]=96, [2786]=69, [2882]=96, [2978]=94, [3074]=96, [3170]=96,
  [3266]=96, [3362]=96, [3458]=96, [3554]=84, [3650]=84, [3746]=96,
  [3842]=96, [3938]=96, [4034]=75, [4130]=96, [4226]=96, [4322]=96,
  [4418]=80, [4514]=82, [4610]=81, [4706]=81, [4802]=90, [4898]=76,
  [4994]=76, [5090]=84, [5186]=96, [5282]=96, [5378]=96,
}

local LOADER_RETURN_PC = 0x66FF
local SCENE_BANK_FIRST = 0x68
local SCENE_BANK_LAST = 0x7F
local SCENE_BYTES = 0x30000
local WINDOW_FRAMES = 240

-- lba -> { touched = {..}, windows = n, events = n }
local per_scene = {}
local pending_lba = nil
local want_lba = nil
local rec_lba = nil
local window_end = 0
local read_id, write_id = nil, nil
local floor = math.floor
local MPR_NAME = {}
for page = 0, 7 do MPR_NAME[page] = "MPR-" .. page end

local function read_dp(a) return memory.read_u8(0x2000 + a, "System Bus") end

local function scene_state(lba)
	local st = per_scene[lba]
	if not st then
		st = { touched = {}, windows = 0, events = 0 }
		per_scene[lba] = st
	end
	return st
end

local function on_access(address)
	local page = floor(address / 0x2000)
	local mpr = emu.getregister(MPR_NAME[page])
	if mpr < SCENE_BANK_FIRST or mpr > SCENE_BANK_LAST then return end
	local st = per_scene[rec_lba]
	st.touched[(mpr - SCENE_BANK_FIRST) * 0x2000 + (address % 0x2000)] = true
	st.events = st.events + 1
end

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	local count = read_dp(0xF8)
	local mode = read_dp(0xFF)
	if mode == 0x06 then
		if SCENES[lba] == count then
			pending_lba = lba
		else
			pending_lba = nil
		end
		if rec_lba then window_end = 0 end
	end
end

local function on_loader_return()
	if pending_lba then
		want_lba = pending_lba
		pending_lba = nil
	end
end

event.on_bus_exec(on_cd_read, 0xE009, "initM CD_READ", "System Bus")
event.on_bus_exec(on_loader_return, LOADER_RETURN_PC, "initM loader ret", "System Bus")

local function emit(lba)
	local st = per_scene[lba]
	local out = assert(io.open(root ..
		string.format("scene_init_coverage_%d.tsv", lba), "w"))
	out:write("format\tZIRIA-SCENE-INIT-COVERAGE-V1\n")
	out:write(string.format("scene_lba\t%d\n", lba))
	out:write(string.format("scene_count\t%d\n", SCENES[lba]))
	out:write(string.format("window_frames\t%d\n", WINDOW_FRAMES))
	out:write(string.format("windows_done\t%d\n", st.windows))
	out:write(string.format("access_events\t%d\n", st.events))
	out:write(string.format("frame\t%d\n", emu.framecount()))
	out:write("offset\tflags256\n")
	local parts = {}
	local total = 0
	for block = 0, SCENE_BYTES / 256 - 1 do
		local base = block * 256
		for j = 0, 255 do
			if st.touched[base + j] then
				parts[j + 1] = "x"; total = total + 1
			else
				parts[j + 1] = "."
			end
		end
		out:write(string.format("%06X\t%s\n", base, table.concat(parts)))
	end
	out:close()
	console.log(string.format("[initM] scene %d saved: windows=%d touched=%d",
		lba, st.windows, total))
end

local function emit_all()
	for lba, st in pairs(per_scene) do
		if st.windows > 0 then emit(lba) end
	end
end
event.onexit(emit_all, "Write init coverage (all)")

console.log("다중 씬 init coverage probe 시작 — 씬 진입마다 자동 기록.")

while true do
	if want_lba and not rec_lba then
		rec_lba = want_lba
		want_lba = nil
		scene_state(rec_lba)
		window_end = emu.framecount() + WINDOW_FRAMES
		read_id = event.on_bus_read(on_access, nil, "initM reads", "System Bus")
		write_id = event.on_bus_write(on_access, nil, "initM writes", "System Bus")
		console.log(string.format("[initM] scene %d RECORDING (느려짐)", rec_lba))
	end
	if rec_lba and emu.framecount() >= window_end then
		local done = rec_lba
		event.unregisterbyid(read_id)
		event.unregisterbyid(write_id)
		local st = per_scene[done]
		st.windows = st.windows + 1
		rec_lba = nil
		emit(done)
		console.log(string.format("[initM] scene %d window #%d done", done, st.windows))
	end
	if rec_lba then
		gui.text(8, 8, string.format(
			"INIT RECORDING scene %d ... %d frames - 대기",
			rec_lba, window_end - emu.framecount()), "yellow")
	else
		local n = 0
		for _ in pairs(per_scene) do n = n + 1 end
		gui.text(8, 8, string.format("init probe idle (scenes=%d)", n), "lime")
	end
	emu.frameadvance()
end
