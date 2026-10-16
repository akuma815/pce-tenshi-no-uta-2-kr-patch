-- 치트 검증: 사본 스테이트 → 치트 스크립트 로드(최고 레벨 끔) → 전투 중 전투 블록 HP 를 피해 직후(onframestart, 치트 쓰기 전)에도 관찰
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local D = "Main Memory"
local function r(a) return memory.read_u8(a, D) end
local log = assert(io.open(OUT .. "cheatverify.log", "w"))
local function say(x) log:write(tostring(x) .. "\n"); log:flush() end
pcall(function() client.speedmode(800) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "user_qs1_2151.State")
dofile(ROOT .. [[\tools\cheat_tenshi2.lua]])
local hits, minhp, battles, inb = 0, {}, 0, false
for f = 1, 6000 do
  local pad = {}
  if (f // 40) % 2 == 0 then pad.Left = true else pad.Right = true end
  if f % 20 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local b = (r(0x1220) + r(0x1221) + r(0x1222) + r(0x1223)) > 0
  if b and not inb then battles = battles + 1; say("battle start f" .. f) end
  if inb and not b then
    local t = {} for i = 0, 3 do t[#t+1] = (r(0x1D7F+i)+r(0x1D83+i)*256) .. "/" .. (r(0x1D87+i)+r(0x1D8B+i)*256) end
    say("battle end f" .. f .. " field HP " .. table.concat(t, " "))
  end
  inb = b
  if b then
    for i = 0, 3 do
      local cur = r(0x121C+i) + r(0x1228+i)*256; local mx = r(0x1234+i) + r(0x1240+i)*256
      if cur < mx then hits = hits + 1 end
    end
  end
  if f % 600 == 0 then pcall(client.screenshot, OUT .. string.format("cv_%05d.png", f)) end
end
say(string.format("battles %d, frames with party battle HP below max at frame end: %d", battles, hits))
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
