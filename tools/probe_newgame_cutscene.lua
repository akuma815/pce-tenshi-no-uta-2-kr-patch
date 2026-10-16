-- 컷신 자막 PoC (2026-10-14): 빈 SaveRAM 으로 부팅 → 새 게임 → 오프닝 비주얼 씬 도달 탐색 (PCEHawk).
-- PROBE_PRESS = 「프레임:버튼,…」(3프레임 유지), PROBE_TOTAL 프레임, PROBE_SHOT 마다 스크린샷, PROBE_SAVEEVERY 마다 스테이트, BIOS CD/ADPCM 호출 프레임 기록.
local OUT = assert(os.getenv("PROBE_OUT")); local TOTAL = tonumber(os.getenv("PROBE_TOTAL") or "6000")
local SHOT = tonumber(os.getenv("PROBE_SHOT") or "30"); local SAVEEVERY = tonumber(os.getenv("PROBE_SAVEEVERY") or "0")
local PRESS = {}
for f, b, l in (os.getenv("PROBE_PRESS") or ""):gmatch("(%d+):(%a+):?(%d*)") do for k = 0, (tonumber(l) or 3) - 1 do PRESS[tonumber(f) + k] = b end end   -- 「프레임:버튼[:길이]」
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/log.txt", "w")); local function say(s) log:write(s .. "\n"); log:flush() end
local ST = os.getenv("PROBE_STATE")
if ST and ST ~= "" then for i = 1, 10 do emu.frameadvance() end; savestate.load(ST); say("loaded " .. ST) end
local F = 0
local BIOS = { [0xE009] = "CD_READ", [0xE012] = "CD_PLAY", [0xE015] = "CD_SEARCH", [0xE018] = "CD_PAUSE", [0xE03C] = "AD_PLAY", [0xE042] = "AD_STOP" }
local n = 0
for a, nm in pairs(BIOS) do
  if pcall(function() event.on_bus_exec(function() say(string.format("f%d %s", F, nm)) end, a, "b" .. nm) end) then n = n + 1 end
end
say("callbacks " .. n)
do local ks = {}; for k, _ in pairs(joypad.get(1)) do ks[#ks + 1] = k end; table.sort(ks); say("buttons " .. table.concat(ks, ",")) end
for f = 1, TOTAL do
  F = f
  if PRESS[f] then joypad.set({[PRESS[f]] = true}, 1); if f % 10 == 0 then say(string.format("f%d press %s", f, PRESS[f])) end end
  emu.frameadvance()
  if f % SHOT == 0 then client.screenshot(OUT .. string.format("/s_%05d.png", f)) end
  if SAVEEVERY > 0 and f % SAVEEVERY == 0 then savestate.save(OUT .. string.format("/at_%05d.State", f)) end
end
say("done"); log:close()
local d = io.open(OUT .. "/done", "w"); d:write("ok"); d:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
