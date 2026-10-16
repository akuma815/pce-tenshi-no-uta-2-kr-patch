-- Z8.9b CDL 세그먼트 캡처 보조 — mode-06 장면 로드 알리미.
--
-- CDL 캡처와 함께 띄워 두는 초경량 스크립트다. $E009(BIOS CD_READ) 단일
-- 주소 exec 훅만 사용하므로 게임 속도에 영향이 없다.
--
-- 화면 표시 (상단 크롭을 피해 y=30):
--   CLEAN  (초록) : 마지막 CDL New 이후 mode-06 장면 로드 없음 → 지금 Save하면 유효
--   DIRTY  (빨강) : mode-06 로드 발생 → 이 세그먼트는 오염. 화면이 안정된 뒤
--                   CDL 창에서 New를 누르면 다시 CLEAN으로 간주
--
-- 사용법:
--   1. PCEHawk로 게임 로드, Tools > Code Data Logger 열기
--   2. 이 스크립트 로드 (Lua Console)
--   3. CDL에서 New를 누른 "직후" 키보드 **Q** 키를 누른다 (게임 입력과 무관)
--   4. CLEAN 상태에서 플레이 → 수시로 Save 덮어쓰기
--   5. DIRTY가 뜨면: 저장하지 말고, 화면 안정 후 CDL New → Q 키
--
-- 주의: 전투는 무로드(캡처 계속), 건물 출입·맵 이동 등은 mode-06 로드다.
--       이 스크립트는 host 파일과 화면 표시만 사용하며 게임 상태를 바꾸지 않는다.

local log_path = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\ziria_z8_9_scene_load_notify_log.tsv]]

local function read_dp(address)
	return memory.read_u8(0x2000 + address, "System Bus")
end

local dirty = false
local load_count = 0
local last_lba, last_count, last_frame = -1, -1, -1
local clean_since_frame = emu.framecount()

local log = assert(io.open(log_path, "a"))
log:write(string.format("# session start frame=%d\n", emu.framecount()))
log:flush()

local function on_cd_read()
	local lba = read_dp(0xFC) * 0x10000 + read_dp(0xFD) * 0x100 + read_dp(0xFE)
	local count = read_dp(0xF8)
	local mode = read_dp(0xFF)
	if mode == 0x06 then
		dirty = true
		load_count = load_count + 1
		last_lba, last_count, last_frame = lba, count, emu.framecount()
		log:write(string.format("%d\tMODE06_LOAD\t%d\t%d\n",
			emu.framecount(), lba, count))
		log:flush()
		console.log(string.format(
			"[z89b] MODE06 LOAD lba=%d count=%d frame=%d -> 세그먼트 오염!",
			lba, count, emu.framecount()))
	end
end

event.on_bus_exec(on_cd_read, 0xE009, "Z89B notify CD_READ", "System Bus")

console.log("Z8.9b 장면 로드 알리미 시작 (감속 없음).")
console.log("CDL New 직후 키보드 Q 키로 CLEAN 리셋하세요.")

while true do
	-- 키보드 Q = "방금 CDL New 눌렀음" 신호 (게임 입력과 무관)
	local keys = input.get()
	if keys and keys["Q"] and dirty then
		dirty = false
		clean_since_frame = emu.framecount()
		log:write(string.format("%d\tSEGMENT_RESET\t-\t-\n", emu.framecount()))
		log:flush()
		console.log("[z89b] 세그먼트 리셋 — CLEAN 상태로 재시작")
	end

	if dirty then
		gui.text(8, 30, string.format(
			"DIRTY: load#%d LBA %d/%d @f%d - Save 금지, CDL New + Q",
			load_count, last_lba, last_count, last_frame), "red")
	else
		gui.text(8, 30, string.format(
			"CLEAN since f%d (loads seen: %d) - Save OK",
			clean_since_frame, load_count), "lime")
	end
	emu.frameadvance()
end
