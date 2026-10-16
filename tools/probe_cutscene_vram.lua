-- 컷신 자막 PoC 조사 (2026-10-14, PCEHawk): 사용자 퀵세이브(컷신 직전 숲) 로드 → 아래로 걸어 컷신 진입 → 일정 간격으로 VRAM·SAT·팔레트·RAM 덤프 + 스크린샷.
-- PROBE_STATE, PROBE_OUT, PROBE_TOTAL, PROBE_DUMPEVERY, PROBE_WALK(아래 누르는 프레임 수)
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local TOTAL = tonumber(os.getenv("PROBE_TOTAL") or "3000"); local EVERY = tonumber(os.getenv("PROBE_DUMPEVERY") or "60")
local WALK = tonumber(os.getenv("PROBE_WALK") or "300")
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/log.txt", "w")); local function say(s) log:write(s .. "\n"); log:flush() end
for i = 1, 10 do emu.frameadvance() end
savestate.load(STATE); say("loaded")
local doms = {}
for _, d in ipairs(memory.getmemorydomainlist()) do say("domain " .. d .. " " .. memory.getmemorydomainsize(d)); doms[#doms + 1] = d end
local F = 0
local BIOS = { [0xE009] = "CD_READ", [0xE012] = "CD_PLAY", [0xE015] = "CD_SEARCH", [0xE018] = "CD_PAUSE" }
for a, nm in pairs(BIOS) do pcall(function() event.on_bus_exec(function() say(string.format("f%d %s", F, nm)) end, a, "b" .. nm) end) end
local function dump(dom, name)
  local n = memory.getmemorydomainsize(dom); local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.char(memory.read_u8(i, dom)) end
  local fh = assert(io.open(name, "wb")); fh:write(table.concat(t)); fh:close()
end
for f = 1, TOTAL do
  F = f
  if f <= WALK then joypad.set({Down = true}, 1) end
  emu.frameadvance()
  if f % EVERY == 0 then
    client.screenshot(OUT .. string.format("/s_%05d.png", f))
    savestate.save(OUT .. string.format("/st_%05d.State", f))
    for _, d in ipairs(doms) do
      if d:find("VRAM") or d == "CPU registers" or d:find("SAT") or d:find("Palette") or d == "Main Memory" or d:find("CD RAM") or d:find("Super System") then
        dump(d, OUT .. string.format("/f%05d_%s.bin", f, d:gsub("[^%w]", "_")))
      end
    end
  end
end
say("done"); log:close()
local d = io.open(OUT .. "/done", "w"); d:write("ok"); d:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
