-- 치트 없이 전투: 0x1D7F HP 배열이 전투 중 피해를 반영하는지 확인 (변화 기록 + 전투 화면 스크린샷)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local D = "Main Memory"
local log = assert(io.open(OUT .. "battlehp.log", "w"))
local function say(x) log:write(tostring(x) .. "\n"); log:flush() end
local function r(a) return memory.read_u8(a, D) end
local function hp() local t = {} for i = 0, 3 do t[#t+1] = (r(0x1D7F+i)+r(0x1D83+i)*256) .. "/" .. (r(0x1D8F+i)+r(0x1D93+i)*256) end return table.concat(t, " ") end
pcall(function() client.speedmode(800) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "user_qs1_2151.State")
local last = hp(); say("start HP/MP " .. last)
local shots = 0
local function dump(dom, path)
  local size = memory.getmemorydomainsize(dom); local fh = assert(io.open(path, "wb"))
  for a = 0, size - 1, 4096 do local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, dom); local t = {}; for i = 1, n do t[i] = string.char(b[i]) end; fh:write(table.concat(t)) end
  fh:close()
end
for f = 1, 3000 do
  local pad = {}
  if (f // 40) % 2 == 0 then pad.Left = true else pad.Right = true end
  if f % 20 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  if f >= 1500 and f <= 2950 and f % 50 == 0 then
    dump("Main Memory", OUT .. string.format("bt_w_%04d.bin", f)); dump("TurboCD RAM", OUT .. string.format("bt_c_%04d.bin", f))
    pcall(client.screenshot, OUT .. string.format("bt_%04d.png", f))
  end
  local s = hp()
  if s ~= last then say("f" .. f .. " " .. s); last = s; if shots < 6 then shots = shots + 1; pcall(client.screenshot, OUT .. string.format("bhp_%d.png", shots)) end end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
