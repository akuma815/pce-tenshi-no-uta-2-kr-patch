-- Z8.9b(v3) — field 장면 "초기화 구간" read/write coverage probe.
--
-- 배경: CDL 세그먼트는 첫 필드가 보인 뒤에 시작하므로, 장면 로드 직후
-- 초기화 단계(그래픽 → VRAM 업로드 등)에서 한 번만 읽히는 바이트가
-- cold로 오판됐다. canary 빌드에서 배경 전면 깨짐으로 실증됨(2026-07-27).
--
-- 이 probe는 평상시 exec 훅 2개($E009, $66FF)만 유지해 감속이 없고,
-- LBA 482/96/mode06 로드가 loader 복귀점 $66FF에 도달한 순간부터
-- WINDOW_FRAMES 동안만 whole-bus read/write 콜백을 등록해 물리
-- bank $68-$7F 접근을 기록한 뒤 콜백을 해제한다.
-- (기록 중에는 게임이 크게 느려지지만 십수 초 창에 한정된다.)
--
-- 사용:
--   1. PCEHawk 코어. ★타이틀 화면에서★ 이 스크립트를 로드
--      (BIOS 화면 중 로드는 이 타이틀을 멈춘 전례가 있음)
--   2. 게임 시작 → 첫 필드 로드 창이 자동 기록(느려짐) 후 정상 속도 복귀
--   3. 건물에 들어갔다 나오기, 첫 전투 후 필드 복귀 등으로
--      LBA 482 재적재 창을 2회 이상 추가 확보
--   4. EmuHawk 정상 종료 → translation/ziria_z8_9_field_init_coverage.tsv
--
-- host 파일 기록 전용. 에뮬레이터 상태·디스크·입력은 변경하지 않는다.

local root = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]
local out_path = root .. [[ziria_z8_9_field_init_coverage.tsv]]

local FIELD_LBA = 482
local FIELD_COUNT = 96
local LOADER_RETURN_PC = 0x66FF
local SCENE_BANK_FIRST = 0x68
local SCENE_BANK_LAST = 0x7F
local SCENE_BYTES = 0x30000
-- 로더 복귀 후 4초(에뮬 시간)만 기록한다. 이 구간이 커버해야 하는 것은
-- "로드 완료 → 화면 표시" 사이의 초기화 read뿐이다. 화면 표시 이후의
-- 접근은 CDL 세그먼트가 담당한다. (900프레임은 느린 상태에서 벽시계
-- 수 분이 걸려 240으로 단축, 2026-07-27)
local WINDOW_FRAMES = 240

local touched = {}
for i = 0, SCENE_BYTES - 1 do touched[i] = false end

local MPR_NAME = {}
for page = 0, 7 do MPR_NAME[page] = "MPR-" .. page end

local pending_field = false
local want_record = false
local recording = false
local window_end = 0
local windows_done = 0
local access_events = 0
local read_id, write_id = nil, nil
local floor = math.floor

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

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
		pending_field = (lba == FIELD_LBA and count == FIELD_COUNT)
		if recording then
			-- 창 안에서 다른 로드가 시작되면 즉시 창을 닫는다(다음 프레임에 해제)
			window_end = 0
		end
		console.log(string.format("[z89b-init] MODE06 lba=%d count=%d pending_field=%s",
			lba, count, tostring(pending_field)))
	end
end

local function on_loader_return()
	if pending_field then
		pending_field = false
		want_record = true
	end
end

event.on_bus_exec(on_cd_read, 0xE009, "Z89Bi CD_READ", "System Bus")
event.on_bus_exec(on_loader_return, LOADER_RETURN_PC, "Z89Bi loader return", "System Bus")

local function emit()
	local out = assert(io.open(out_path, "w"))
	out:write("format\tZIRIA-Z8-9-FIELD-INIT-COVERAGE-V1\n")
	out:write(string.format("scene_lba\t%d\n", FIELD_LBA))
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
				parts[j + 1] = "x"
				total = total + 1
			else
				parts[j + 1] = "."
			end
		end
		out:write(string.format("%06X\t%s\n", base, table.concat(parts)))
	end
	out:close()
	console.log(string.format("[z89b-init] report: windows=%d touched=%d/%d",
		windows_done, total, SCENE_BYTES))
end

event.onexit(emit, "Write Z8.9b init coverage")

console.log("Z8.9b field 초기화 coverage probe 시작 (평상시 무감속).")
console.log(string.format(
	"LBA 482 로드 복귀 직후 %d프레임(에뮬 %d초)만 기록하며 그동안 느려집니다.",
	WINDOW_FRAMES, WINDOW_FRAMES / 60))

while true do
	if want_record and not recording then
		want_record = false
		recording = true
		window_end = emu.framecount() + WINDOW_FRAMES
		read_id = event.on_bus_read(on_access, nil, "Z89Bi reads", "System Bus")
		write_id = event.on_bus_write(on_access, nil, "Z89Bi writes", "System Bus")
		console.log(string.format("[z89b-init] RECORDING start frame=%d (느려짐)", emu.framecount()))
	end
	if recording and emu.framecount() >= window_end then
		recording = false
		event.unregisterbyid(read_id)
		event.unregisterbyid(write_id)
		windows_done = windows_done + 1
		emit()
		console.log(string.format("[z89b-init] window #%d done frame=%d (정상 속도 복귀)",
			windows_done, emu.framecount()))
	end
	if recording then
		gui.text(8, 8, string.format(
			"INIT RECORDING #%d ... %d프레임 남음 - 버튼 누르지 말고 대기",
			windows_done + 1, window_end - emu.framecount()), "yellow")
	else
		gui.text(8, 8, string.format("idle (windows=%d, events=%d)",
			windows_done, access_events), "lime")
	end
	emu.frameadvance()
end
