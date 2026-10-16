-- 전투 즉시 종료 치트 검증 (2026-10-11): PROBE_STATE 로드 → cheat_tenshi2.lua(전투 즉시 종료 포함) → 좌우로 걸어 전투 → I 반복 → 필드 복귀(0x0005 = 0x80)까지 프레임 기록.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local ROOT = [[G:/Downloads/Korean Traslate Project/Games/Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local D = "Main Memory"; local function r(a) return memory.read_u8(a, D) end
local log = assert(io.open(OUT .. "/instant.log", "w")); local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
pcall(function() client.speedmode(400) end)
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE); emu.frameadvance()
dofile(ROOT .. "/tools/cheat_tenshi2.lua")
local phase, fb, ends = "walk", 0, 0
for f = 1, 6000 do
  local btn = {}
  if phase == "walk" then if ((f // 60) % 2 == 0) then btn.Left = true else btn.Right = true end
  else if f % 12 < 3 then btn.I = true end end
  joypad.set(btn, 1)
  emu.frameadvance()
  local inb = (r(0x0005) == 0)
  if phase == "walk" and inb then phase = "battle"; fb = f; say("battle start f" .. f) end
  if phase == "battle" then
    if (f - fb) % 60 == 0 then
      local hp = {} for e = 4, 11 do if (r(0x1234 + e) + r(0x1240 + e)) > 0 then hp[#hp + 1] = r(0x121C + e) + r(0x1228 + e) * 256 end end
      say(string.format("f%d enemyHP=%s", f, table.concat(hp, ","))); client.screenshot(OUT .. string.format("/b_%05d.png", f))
    end
    if not inb and f - fb > 30 then say("battle end f" .. f .. " (" .. (f - fb) .. " frames)"); client.screenshot(OUT .. "/after.png"); ends = ends + 1; phase = "walk"; if ends >= 2 then break end end
  end
end
say("done ends=" .. ends); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
