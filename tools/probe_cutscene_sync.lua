-- 이벤트 영상 싱크 관찰 (2026-10-11 사용자: 「이벤트 영상이랑 음성 싱크가 안 맞아」 — 퀵세이브 1 → 위로 이동 → 대사 → 영상).
-- PROBE_STATE 로드 → PROBE_DIR 을 PROBE_HOLD 프레임 → PROBE_PRESS(「프레임:버튼,…」) 대로 1프레임씩 누름 → PROBE_WAIT 프레임까지 관찰.
-- 기록: BIOS CD/ADPCM 호출(실행 콜백, 프레임 번호), 매 프레임 화면 변화량(이전 프레임 대비 다른 픽셀 비율 — 영상 진행 지표), PROBE_SHOT 프레임마다 스크린샷.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local DIR = os.getenv("PROBE_DIR") or "Up"; local HOLD = tonumber(os.getenv("PROBE_HOLD") or "20")
local WAIT = tonumber(os.getenv("PROBE_WAIT") or "2400"); local SHOT = tonumber(os.getenv("PROBE_SHOT") or "15")
local PRESS = {}
local DUMPAT = {}
local SAVEAT = {}
for f in (os.getenv("PROBE_SAVEAT") or ""):gmatch("(%d+)") do SAVEAT[tonumber(f)] = true end
for f in (os.getenv("PROBE_DUMPAT") or ""):gmatch("(%d+)") do DUMPAT[tonumber(f)] = true end
for f, b in (os.getenv("PROBE_PRESS") or ""):gmatch("(%d+):(%a+)") do PRESS[tonumber(f)] = b end
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/sync.log", "w")); local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE)
-- PROBE_POKES = 「도메인<TAB>주소hex<TAB>바이트hex」 줄 파일(make_state_to_original.py) — 로드 직후 적용, PROBE_SAVE 가 있으면 그 상태로 저장(원본 디스크 A/B 용)
local PK = os.getenv("PROBE_POKES")
if PK and PK ~= "" then
  local n = 0
  for line in io.lines(PK) do
    local dom, a, b = line:match("^([^	]+)	(%x+)	(%x+)$")
    if dom then memory.write_u8(tonumber(a, 16), tonumber(b, 16), dom); n = n + 1 end
  end
  say("pokes applied " .. n)
  local SV = os.getenv("PROBE_SAVE"); if SV and SV ~= "" then savestate.save(SV); say("saved " .. SV) end
end
emu.frameadvance()
local F = 0
local BIOS = { [0xE009] = "CD_READ", [0xE00C] = "CD_SEEK", [0xE012] = "CD_PLAY", [0xE015] = "CD_SEARCH", [0xE018] = "CD_PAUSE",
  [0xE030] = "AD_RESET", [0xE033] = "AD_TRANS", [0xE036] = "AD_READ", [0xE039] = "AD_WRITE", [0xE03C] = "AD_PLAY", [0xE03F] = "AD_CPLAY", [0xE042] = "AD_STOP", [0xE045] = "AD_STAT" }
local okcb = 0
for a, n in pairs(BIOS) do
  local ok = pcall(function() event.onmemoryexecute(function() say(string.format("f%d %s", F, n)) end, a, "bios" .. n) end)
  if ok then okcb = okcb + 1 end
end
say("exec callbacks registered " .. okcb)
for f = 1, HOLD + WAIT do
  F = f
  if f <= HOLD then joypad.set({[DIR] = true}, 1) end
  if PRESS[f] then joypad.set({[PRESS[f]] = true}, 1) end
  emu.frameadvance()
  if f % SHOT == 0 then client.screenshot(OUT .. string.format("/s_%05d.png", f)) end
  if SAVEAT[f] then savestate.save(OUT .. string.format("/at_f%05d.State", f)); say(string.format("saved at f%d", f)) end
  if DUMPAT[f] then   -- PROBE_DUMPAT 프레임에 RAM 덤프(어느 모듈이 올라와 있는지 디스크 대조용)
    for _, dom in ipairs({"TurboCD RAM", "Super System Card RAM", "Main Memory"}) do
      local fh = assert(io.open(OUT .. string.format("/f%05d_%s.bin", f, dom:gsub("[^%w]", "_")), "wb")); local t = {}
      for i = 0, memory.getmemorydomainsize(dom) - 1 do t[#t + 1] = string.char(memory.read_u8(i, dom)) end
      fh:write(table.concat(t)); fh:close()
    end
  end
  if f % 60 == 0 then say(string.format("f%d mode0005=%02X FLAG=%02X", f, memory.read_u8(0x0005, "Main Memory"), cd(0x88F9))) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
