-- ★ DEPRECATED (2026-07-27): whole-bus 콜백이 게임을 플레이 불가 속도로
-- 만들어 폐기. 또한 field 재적재 시 BIOS의 CPU 복사가 write coverage를
-- 전량 오염시키는 결함이 있다. 대체 경로는 PCEHawk 내장 Code Data Logger
-- 세그먼트 캡처 + tools/analyze_ziria_z8_9_cdl_coverage.py 다.
--
-- Z8.9b scene RAM read/write coverage probe (read-only host logger).
--
-- 목적: field 시작 장면(LBA 482, 96 sectors, mode 06)이 상주하는 동안
--       물리 bank $68-$7F(192 KiB scene RAM)에서 CPU가 한 번도
--       read/write 하지 않은 바이트 구간(cold region 후보)을 찾는다.
--       cold = read 0회 AND write 0회. (엔진이 쓰는 작업 버퍼도
--       번역 데이터를 파괴하므로 write도 제외 조건이다.)
--
-- ★★ 반드시 PCEHawk 코어로 실행할 것 ★★ (TurboNyma는 메모리 콜백 미지원)
-- ★★ 첫 필드가 화면에 보인 뒤 이 스크립트를 수동으로 열 것 ★★
--     (BIOS 화면 중 Lua 로드는 과거 이 타이틀을 멈추게 했다.
--      따라서 초기 장면 identity는 명시적 field-start 가정으로 시작하고,
--      다음 mode-06 CD read부터 관측값으로 대체한다.)
--
-- 이 스크립트는 host 파일만 기록한다. 에뮬레이터 메모리 쓰기, 입력 주입,
-- 스테이트 로드, 디스크 수정은 하지 않는다.
--
-- 권장 주행 경로(Z8.9b 게이트):
--   첫 대사 → 마을 NPC 전원 대화 → Memo 진입·복귀 → 첫 전투·필드 복귀
--   → 탑 진입 → (탑에서 필드 복귀가 있으면 복귀) → 필드 재진입 반복.
--   field 장면(482)이 활성일 때만 coverage가 누적된다.

local root = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\]]
local coverage_path = root .. [[ziria_z8_9_scene_ram_coverage.tsv]]
local runs_path = root .. [[ziria_z8_9_scene_ram_cold_runs.tsv]]
local status_path = root .. [[ziria_z8_9_scene_ram_coverage_status.txt]]

local FIELD_LBA = 482
local FIELD_COUNT = 96
local SCENE_BANK_FIRST = 0x68
local SCENE_BANK_LAST = 0x7F
local SCENE_BYTES = (SCENE_BANK_LAST - SCENE_BANK_FIRST + 1) * 0x2000  -- 0x30000
local MIN_RUN = 32            -- 리포트할 최소 연속 cold 길이(바이트)
local FLUSH_SECONDS = 30

-- 0=untouched, 1=read, 2=write, 3=both
local cover = {}
for i = 0, SCENE_BYTES - 1 do cover[i] = 0 end

local MPR_NAME = {}
for page = 0, 7 do MPR_NAME[page] = "MPR-" .. page end

local field_active = true      -- manual field-visible start assumption
local scene_identity_source = "manual_field_visible_assumption"
local active_lba, active_count, active_mode = FIELD_LBA, FIELD_COUNT, 0x06
local field_generations = 1    -- field 장면이 활성화된 횟수
local cd_records = 0
local read_events, write_events = 0, 0
local active_frames_hint = 0

local floor = math.floor

local function on_read(address)
	if not field_active then return end
	local page = floor(address / 0x2000)
	local mpr = emu.getregister(MPR_NAME[page])
	if mpr < SCENE_BANK_FIRST or mpr > SCENE_BANK_LAST then return end
	local i = (mpr - SCENE_BANK_FIRST) * 0x2000 + (address % 0x2000)
	local c = cover[i]
	if c == 0 then cover[i] = 1
	elseif c == 2 then cover[i] = 3 end
	read_events = read_events + 1
end

local function on_write(address)
	if not field_active then return end
	local page = floor(address / 0x2000)
	local mpr = emu.getregister(MPR_NAME[page])
	if mpr < SCENE_BANK_FIRST or mpr > SCENE_BANK_LAST then return end
	local i = (mpr - SCENE_BANK_FIRST) * 0x2000 + (address % 0x2000)
	local c = cover[i]
	if c == 0 then cover[i] = 2
	elseif c == 1 then cover[i] = 3 end
	write_events = write_events + 1
end

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	local count = read_dp(0xF8)
	local mode = read_dp(0xFF)
	cd_records = cd_records + 1
	if mode == 0x06 then
		local was_active = field_active
		active_lba, active_count, active_mode = lba, count, mode
		field_active = (lba == FIELD_LBA and count == FIELD_COUNT)
		scene_identity_source = "observed_mode06_cd_read"
		if field_active and not was_active then
			field_generations = field_generations + 1
		end
	end
	console.log(string.format(
		"Z89B CD_READ lba=%d count=%d mode=%02X field_active=%s",
		lba, count, mode, tostring(field_active)))
end

local SYMBOL = { [0] = ".", [1] = "r", [2] = "w", [3] = "b" }

local function emit_reports()
	-- 바이트 단위 coverage를 256바이트/행 심볼 문자열로 기록한다.
	local out = assert(io.open(coverage_path, "w"))
	out:write("format\tZIRIA-Z8-9-SCENE-RAM-COVERAGE-V1\n")
	out:write(string.format("scene_lba\t%d\n", FIELD_LBA))
	out:write(string.format("scene_count\t%d\n", FIELD_COUNT))
	out:write(string.format("bank_first\t%02X\n", SCENE_BANK_FIRST))
	out:write(string.format("bank_last\t%02X\n", SCENE_BANK_LAST))
	out:write(string.format("frame\t%d\n", emu.framecount()))
	out:write(string.format("field_generations\t%d\n", field_generations))
	out:write(string.format("read_events\t%d\n", read_events))
	out:write(string.format("write_events\t%d\n", write_events))
	out:write(string.format("cd_records\t%d\n", cd_records))
	out:write(string.format("scene_identity_source\t%s\n", scene_identity_source))
	out:write("offset\tflags256\n")
	local parts = {}
	for block = 0, SCENE_BYTES / 256 - 1 do
		local base = block * 256
		for j = 0, 255 do parts[j + 1] = SYMBOL[cover[base + j]] end
		out:write(string.format("%06X\t%s\n", base, table.concat(parts)))
	end
	out:close()

	-- cold run 요약(사람 확인용; 정본은 coverage 파일)
	local runs = assert(io.open(runs_path, "w"))
	runs:write("offset_start\toffset_end_exclusive\tlength\tbank_start\tbank_offset\n")
	local run_start, cold_total, longest = nil, 0, 0
	for i = 0, SCENE_BYTES do
		local cold = i < SCENE_BYTES and cover[i] == 0
		if cold then cold_total = cold_total + 1 end
		if cold and run_start == nil then
			run_start = i
		elseif not cold and run_start ~= nil then
			local length = i - run_start
			if length >= MIN_RUN then
				runs:write(string.format("%06X\t%06X\t%d\t%02X\t%04X\n",
					run_start, i, length,
					SCENE_BANK_FIRST + floor(run_start / 0x2000),
					run_start % 0x2000))
			end
			if length > longest then longest = length end
			run_start = nil
		end
	end
	runs:close()

	local status = assert(io.open(status_path, "w"))
	status:write(string.format(
		"status=running\nframe=%d\nfield_active=%s\nfield_generations=%d\n"
		.. "read_events=%d\nwrite_events=%d\ncd_records=%d\n"
		.. "cold_bytes=%d\nscene_bytes=%d\nlongest_cold_run=%d\n"
		.. "active_lba=%d\nactive_count=%d\nscene_identity_source=%s\n",
		emu.framecount(), tostring(field_active), field_generations,
		read_events, write_events, cd_records,
		cold_total, SCENE_BYTES, longest,
		active_lba, active_count, scene_identity_source))
	status:close()

	console.log(string.format(
		"[z89b] frame=%d gen=%d cold=%d/%d longest=%d r=%d w=%d",
		emu.framecount(), field_generations, cold_total, SCENE_BYTES, longest,
		read_events, write_events))
end

event.on_bus_read(on_read, nil, "Z89B scene RAM reads", "System Bus")
event.on_bus_write(on_write, nil, "Z89B scene RAM writes", "System Bus")
event.on_bus_exec(on_cd_read, 0xE009, "Z89B CD_READ", "System Bus")
event.onexit(emit_reports, "Write Z8.9b coverage reports")

console.log("Z8.9b scene RAM coverage probe active: banks $68-$7F, field LBA 482 gate")
console.log("첫 필드가 보이는 상태에서 시작했는지 확인. 종료 시 최종 리포트 기록.")

local next_flush = os.time() + FLUSH_SECONDS
while true do
	emu.frameadvance()
	if os.time() >= next_flush then
		emit_reports()
		next_flush = os.time() + FLUSH_SECONDS
	end
end
