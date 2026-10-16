-- 씬별(윈도우) Work RAM write-생존성 트레이서 (PCEHawk 코어 필요).
--
-- 목적: 18개 오버플로 area가 로드된 "그 씬 동안만" $2000..$3FFF 에서 자유로운(=한 번도
--       쓰이지 않은) 연속 구간을 잰다. 전역 트레이스(Step 28)는 모든 씬의 합집합이라
--       과도하게 비관적이므로, 씬 경계로 윈도우를 끊어 씬별로 측정한다.
--
-- 방법: BIOS CD_READ($E009) 실행을 감시해 대상 area LBA가 로드되면 그 시점부터 새 윈도우를
--       열고(ever_written 리셋), 다음 씬 로드까지 매 프레임 Work RAM 쓰기를 프레임-diff로 누적.
--       윈도우가 닫힐 때 그 씬(LBA)의 자유 연속구간을 기록한다.
--
-- 플레이 요령: 각 오버플로 씬에 들어가면 그 지역의 대사/이벤트를 충분히 진행(텍스트가 실제로
--             출력되게)한 뒤 다음 지역으로 이동. 큰 6개(LBA 866/2306/962/482/1346/1826) 우선.
--
-- 사용: run_liveness_trace.ps1 -Scene   또는
--       EmuHawk.exe --lua="...\trace_scene_scratch.lua" "...\원본.cue"   (코어=PCEHawk)

local out_path = [[G:\Downloads\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\scene_scratch.tsv]]
local base, size = 0x2000, 0x2000
local reserved_end = 0x2200          -- $2000..$21FF(제로페이지+스택)은 후보 제외
local min_run = 32
local flush_seconds = 15

-- 18개 오버플로 area 로드 LBA (데이터트랙 상대). count>=80 인 CD_READ만 씬 로드로 인정.
local targets = {}
for _, lba in ipairs({290,386,482,674,770,866,962,1154,1250,1346,1602,1634,1826,1922,2306,2690,2850,3938}) do
	targets[lba] = true
end

local function read8(a) return memory.read_u8(0x2000 + a, "System Bus") end

local ever, prev = {}, nil
local cur_lba, win_start_frame = nil, 0
local out = assert(io.open(out_path, "w"))
out:write("lba\twindow_frames\tlargest_free\ttotal_free\tnum_runs\truns(start:len,...)\n")
out:flush()

local function reset_window(lba)
	for i = 0, size - 1 do ever[i] = false end
	prev = memory.read_bytes_as_array(base, size, "System Bus")
	cur_lba = lba
	win_start_frame = emu.framecount()
end

local function free_runs()
	local runs, s = {}, nil
	local largest, total = 0, 0
	for i = 0, size do
		local free = i < size and (base + i) >= reserved_end and not ever[i]
		if free then total = total + 1 end
		if free and s == nil then s = i
		elseif (not free) and s ~= nil then
			local len = i - s
			if len >= min_run then runs[#runs+1] = string.format("%04X:%d", base + s, len) end
			if len > largest then largest = len end
			s = nil
		end
	end
	return runs, largest, total
end

local function close_window()
	if cur_lba == nil then return end
	local runs, largest, total = free_runs()
	out:write(string.format("%d\t%d\t%d\t%d\t%d\t%s\n",
		cur_lba, emu.framecount() - win_start_frame, largest, total, #runs,
		table.concat(runs, ",")))
	out:flush()
	console.log(string.format("[scene %d] frames=%d largest_free=%d total_free=%d",
		cur_lba, emu.framecount() - win_start_frame, largest, total))
end

local function on_cd_read()
	local lba = read8(0xFC) * 0x10000 + read8(0xFD) * 0x100 + read8(0xFE)
	local count = read8(0xF8)
	if targets[lba] and count >= 80 and lba ~= cur_lba then
		close_window()          -- 직전 씬 윈도우 마감
		reset_window(lba)       -- 새 씬 윈도우 시작
		console.log(string.format(">> scene load LBA=%d count=%d — window start", lba, count))
	end
end

local function scan()
	if cur_lba == nil then return end
	local cur = memory.read_bytes_as_array(base, size, "System Bus")
	for i = 0, size - 1 do
		if cur[i+1] ~= prev[i+1] then ever[i] = true end
	end
	prev = cur
end

event.on_bus_exec(on_cd_read, 0xE009, "scene CD_READ", "System Bus")
event.onexit(function() close_window(); out:close() end, "close scene scratch")

console.log("Scene scratch tracer active (PCEHawk 필요). 오버플로 씬에 들어가 대사를 진행하세요.")
local next_flush = os.time() + flush_seconds
while true do
	scan()
	emu.frameadvance()
	if os.time() >= next_flush then
		-- 진행 중 윈도우도 중간 기록(덮어쓰지 않고 콘솔로만)
		if cur_lba then
			local _, largest, total = free_runs()
			console.log(string.format("[scene %d ...] largest_free=%d total_free=%d", cur_lba, largest, total))
		end
		next_flush = os.time() + flush_seconds
	end
end
