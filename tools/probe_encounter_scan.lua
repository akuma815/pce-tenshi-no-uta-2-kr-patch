-- 랜덤 인카운터 카운터 탐색 (2026-10-11): PROBE_STATE 로드 → 좌우로만 걷기(사용자 지시: 상하 금지) → 전투 시작까지 Main Memory 를 4프레임마다 기록.
-- PROBE_FREEZE="주소=값" 이면 그 바이트를 매 프레임 고정하고 PROBE_MAXF 프레임 동안 전투가 나는지만 본다(검증 모드).
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local FIRST = os.getenv("PROBE_FIRST") or "Left"; local SEG = tonumber(os.getenv("PROBE_SEG") or "40")
local MAXF = tonumber(os.getenv("PROBE_MAXF") or "6000"); local FREEZE = os.getenv("PROBE_FREEZE") or ""
local SNAPFROM = tonumber(os.getenv("PROBE_SNAPFROM") or "0")   -- 0 이면 4프레임 간격, N 이면 N 프레임부터 매 프레임
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local D = "Main Memory"
local log = assert(io.open(OUT .. "/scan.log", "w")); local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local freeze = {}
for a, v in FREEZE:gmatch("(%x+)=(%x+)") do freeze[#freeze + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local fa = (#freeze > 0) and true or nil
local cdfreeze = {}   -- PROBE_CDFREEZE = "주소=값;…" (TurboCD RAM, 코드 패치 시험)
for a, v in (os.getenv("PROBE_CDFREEZE") or ""):gmatch("(%x+)=(%x+)") do cdfreeze[#cdfreeze + 1] = {tonumber(a, 16), tonumber(v, 16)}; fa = true end
pcall(function() client.speedmode(800) end)
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE); emu.frameadvance()
local SECOND = (FIRST == "Left") and "Right" or "Left"
local snap = (fa == nil) and assert(io.open(OUT .. "/snaps.bin", "wb")) or nil
local n = 0
-- 전투 판정: 전투 블록(0x121C-0x127B, 12칸 HP/최대HP/MP/최대MP)이 로드 직후 값에서 바뀌면 전투 시작(필드에선 직전 전투 값이 남아 있음)
local base = {} for a = 0x121C, 0x127B do base[a] = memory.read_u8(a, D) end
local s05 = memory.read_u8(0x0005, D)
local function battle()
  -- 전투 판정(2026-10-11 실측): 0x0005(CPU $2005) 가 필드 내내 0x80, 전투 진입 직전 0x00. 전투 블록·0x1B8F·0x116D 는 직전 전투 값 잔존/걷기 변동으로 부정확
  return memory.read_u8(0x0005, D) ~= s05
end
for f = 1, MAXF do
  local dir = ((f // SEG) % 2 == 0) and FIRST or SECOND
  joypad.set({[dir] = true}, 1)
  for _, fz in ipairs(freeze) do memory.write_u8(fz[1], fz[2], D) end
  for _, fz in ipairs(cdfreeze) do memory.write_u8(fz[1], fz[2], "TurboCD RAM") end
  emu.frameadvance()
  if snap and ((SNAPFROM == 0 and f % 4 == 0) or (SNAPFROM > 0 and f >= SNAPFROM)) then local t = {} for a = 0, 0x1FFF do t[#t + 1] = string.char(memory.read_u8(a, D)) end; snap:write(table.concat(t)); n = n + 1 end
  if battle() then say("battle at f" .. f .. " samples=" .. n); client.screenshot(OUT .. "/battle.png"); break end
  if f % 600 == 0 then client.screenshot(OUT .. string.format("/walk_%05d.png", f)) end
  if f == MAXF then say("no battle in " .. MAXF .. " frames samples=" .. n); client.screenshot(OUT .. "/end.png") end
end
if snap then snap:close() end
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
