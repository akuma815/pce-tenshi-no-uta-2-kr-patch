-- PC Engine Work RAM ($2000..$3FFF) byte-liveness tracer for BizHawk (EmuHawk).
--
-- 목적: 게임을 대표 장면들로 플레이하면서 CPU가 한 번도 read/write 하지 않은
--       Work RAM 바이트(=후킹용 스크래치 후보)를 찾는다.
--
-- ★★ 반드시 PCEHawk 코어로 실행할 것 ★★
--   * PCEHawk(PCEngine C# 코어)만 read/write 메모리 콜백을 발생시킨다
--     (HuC6280.ReadMemory/WriteMemory(16bit) → "System Bus" 콜백. 페치도 ReadMemory라 실행까지 커버).
--   * TurboNyma(Mednafen waterbox)는 MemoryCallbacks 배선이 없어 이 트레이서가 조용히 실패한다.
--   * EmuHawk 메뉴 Config→Cores→PCE-CD 를 PCEHawk 로 바꾼 뒤 게임을 로드할 것
--     (또는 output/config.ini 의 "PCECD":"TurboNyma" → "PCEHawk").
--   * 콜백 매칭은 선형 스캔이라 whole-bus 단일 콜백 + Lua 필터가 최적(주소별 등록 금지).
--
-- 사용(코어를 PCEHawk로 설정한 뒤):
--   EmuHawk.exe --lua="...\tools\trace_work_ram_liveness.lua" "...\원본.cue"
--   대표 장면(타이틀→뉴게임→마을→대사 여러 개→메뉴→전투→씬전환 20회 이상)을 플레이한 뒤
--   EmuHawk를 정상 종료하면 최종 리포트가 기록된다. 30초마다 중간 저장도 된다.

local raw_path  = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\work_ram_liveness.tsv]]
local runs_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\work_ram_untouched_runs.tsv]]
local base = 0x2000
local size = 0x2000          -- 8 KiB Work RAM ($2000..$3FFF)
local minimum_run = 64        -- 리포트할 최소 연속 미접근 길이(작게 잡아 세밀히 본다)
local flush_seconds = 15      -- 실시간 N초마다 중간 저장(저속 fps에서도 증거 보존)

local reads, writes, first_frame, last_frame = {}, {}, {}, {}
for i = 0, size - 1 do
	reads[i], writes[i], first_frame[i], last_frame[i] = 0, 0, -1, -1
end

local function record(address, is_write)
	if address < base or address >= base + size then return end
	local i = address - base
	if is_write then writes[i] = writes[i] + 1 else reads[i] = reads[i] + 1 end
	local frame = emu.framecount()
	if first_frame[i] < 0 then first_frame[i] = frame end
	last_frame[i] = frame
end

local function on_read(address, value, flags)  record(address, false) end
local function on_write(address, value, flags) record(address, true)  end

local function emit_reports()
	local raw = assert(io.open(raw_path, "w"))
	raw:write("address\treads\twrites\tfirst_frame\tlast_frame\n")
	for i = 0, size - 1 do
		raw:write(string.format("%04X\t%d\t%d\t%d\t%d\n",
			base + i, reads[i], writes[i], first_frame[i], last_frame[i]))
	end
	raw:close()

	local runs = assert(io.open(runs_path, "w"))
	runs:write("start\tend_exclusive\tlength\n")
	local run_start, longest, total_untouched = nil, 0, 0
	for i = 0, size do
		local untouched = i < size and reads[i] == 0 and writes[i] == 0
		if untouched then total_untouched = total_untouched + 1 end
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
	console.log(string.format("[liveness] frame=%d untouched=%d/%d longest_run=%d",
		emu.framecount(), total_untouched, size, longest))
end

event.on_bus_read(on_read,  nil, "Trace Work RAM reads",  "System Bus")
event.on_bus_write(on_write, nil, "Trace Work RAM writes", "System Bus")
event.onexit(emit_reports, "Write Work RAM liveness reports")

console.log("Work RAM liveness tracer active: $2000..$3FFF")
console.log("대표 장면을 플레이한 뒤 EmuHawk를 정상 종료하세요. 30초마다 중간 저장됩니다.")

local next_flush = os.time() + flush_seconds
while true do
	emu.frameadvance()
	if os.time() >= next_flush then
		emit_reports()
		next_flush = os.time() + flush_seconds
	end
end
