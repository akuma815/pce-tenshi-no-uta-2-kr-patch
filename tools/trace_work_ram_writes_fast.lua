-- PC Engine Work RAM ($2000..$3FFF) 고속 write-생존성 트레이서 (프레임 diff 방식).
--
-- whole-bus 콜백 트레이서(trace_work_ram_liveness.lua)는 정확하지만 매 접근마다 Lua가
-- 호출돼 극도로 느리다. 이 스크립트는 콜백을 쓰지 않고 매 프레임 Work RAM 8KB를 통째로
-- 읽어 이전 프레임과 비교, "값이 바뀐(=쓰여진) 바이트"를 표시한다. 거의 풀스피드로 돈다.
--
-- 한계: (1) 읽기는 감지 못 함. (2) 같은 값을 다시 쓰는 write는 안 보임.
--       스크래치 안전성의 핵심 신호는 "게임이 여기에 한 번도 안 쓴다"이므로 1차 스크리닝에 충분.
--       확정은 콜백 트레이서로 교차검증할 것.
--
-- ★ PCEHawk 코어 권장(메모리 도메인 읽기는 두 코어 다 되지만, 콜백 버전과 결과를 맞추려면 동일 코어).
--
-- 사용: EmuHawk.exe --lua="...\trace_work_ram_writes_fast.lua" "...\원본.cue"
--   대표 장면을 폭넓게 플레이한 뒤 정상 종료. 15초마다 중간 저장.

local raw_path  = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\work_ram_writes_fast.tsv]]
local runs_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\work_ram_untouched_runs.tsv]]
local base = 0x2000
local size = 0x2000
local minimum_run = 64
local flush_seconds = 15

local ever_written = {}   -- i -> true(값이 바뀐 적 있음)
local write_frame  = {}   -- i -> 최초로 바뀐 프레임
for i = 0, size - 1 do ever_written[i] = false end

local prev = memory.read_bytes_as_array(base, size, "System Bus")

local function scan()
	local cur = memory.read_bytes_as_array(base, size, "System Bus")
	local frame = emu.framecount()
	-- read_bytes_as_array는 1-기반 배열
	for i = 0, size - 1 do
		if cur[i + 1] ~= prev[i + 1] and not ever_written[i] then
			ever_written[i] = true
			write_frame[i] = frame
		end
	end
	prev = cur
end

local function emit_reports()
	local raw = assert(io.open(raw_path, "w"))
	raw:write("address\twritten\tfirst_write_frame\n")
	for i = 0, size - 1 do
		raw:write(string.format("%04X\t%d\t%d\n",
			base + i, ever_written[i] and 1 or 0, write_frame[i] or -1))
	end
	raw:close()

	local runs = assert(io.open(runs_path, "w"))
	runs:write("start\tend_exclusive\tlength\n")
	local run_start, longest, total = nil, 0, 0
	for i = 0, size do
		local untouched = i < size and not ever_written[i]
		if untouched then total = total + 1 end
		if untouched and run_start == nil then
			run_start = i
		elseif not untouched and run_start ~= nil then
			local length = i - run_start
			if length >= minimum_run then
				runs:write(string.format("%04X\t%04X\t%d\n", base + run_start, base + i, length))
			end
			if length > longest then longest = length end
			run_start = nil
		end
	end
	runs:close()
	console.log(string.format("[fast-writes] frame=%d never_written=%d/%d longest_run=%d",
		emu.framecount(), total, size, longest))
end

event.onexit(emit_reports, "Write fast write-liveness reports")
console.log("Fast Work RAM write-liveness (frame diff): $2000..$3FFF")
console.log("대표 장면을 폭넓게 플레이한 뒤 EmuHawk를 정상 종료하세요. 15초마다 중간 저장.")

local next_flush = os.time() + flush_seconds
while true do
	scan()
	emu.frameadvance()
	if os.time() >= next_flush then
		emit_reports()
		next_flush = os.time() + flush_seconds
	end
end
