-- PCEHawk(원본 디스크): 카드 미니게임 타일맵(lo/hi 평면) RAM 버퍼 셀에 대한 쓰기 → PC/MPR/스택 복귀주소 로그
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUT .. "/map_writes.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local function rd(a) return memory.read_u8(a, BUS) end
local armed, n = false, 0
local function onw(addr, val)
  if not armed or n > 3000 then return end
  n = n + 1
  local s = reg("S"); local rets = {}
  for k = 1, 6 do rets[#rets+1] = string.format("%04X", rd(0x2100 + ((s + 2*k - 1) % 256)) + rd(0x2100 + ((s + 2*k) % 256)) * 256) end
  say(string.format("f%d PC=%04X a=%04X v=%02X m2=%02X m3=%02X m4=%02X m5=%02X m6=%02X m7=%02X ret=%s", emu.framecount(), reg("PC"), addr, val,
    reg("MPR-2"), reg("MPR-3"), reg("MPR-4"), reg("MPR-5"), reg("MPR-6"), reg("MPR-7"), table.concat(rets, ",")))
end
for _, lo in ipairs({0x4B5, 0xCC7, 0x4D5, 0xCE7}) do
  for _, hi in ipairs({0x2000, 0x4000, 0x6000, 0x8000, 0xA000, 0xC000}) do
    event.on_bus_write(onw, hi + lo, string.format("w%04X", hi + lo), BUS)
  end
end
local function batsum()
  local b = memory.read_bytes_as_array(0, 4096, "VRAM1"); local h = 0
  for i = 1, #b do h = (h * 31 + b[i]) % 1000000007 end
  return h
end
pcall(function() client.speedmode(400) end)
local slot = tonumber(os.getenv("CG_SLOT") or "6")
local p = SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave" .. slot .. ".State"
for i = 1, 30 do emu.frameadvance() end
savestate.load(p)
for i = 1, 5 do emu.frameadvance() end
armed = true
say("loaded slot " .. slot .. " frame=" .. emu.framecount())
local presses = {}
for b in (os.getenv("CG_BTNS") or "Select,B2,B1,Run"):gmatch("[^,]+") do presses[#presses+1] = b end
for i, btn in ipairs(presses) do
  local f0 = emu.framecount(); local n0 = n; local h0 = batsum()
  for f = 1, 3 do pcall(joypad.set, {[btn] = true}, 1); emu.frameadvance() end
  for f = 1, 90 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/m_s%d_after_%d_%s.png", slot, i, btn))
  say(string.format("press %s at f%d: map writes %d  BAT changed=%s", btn, f0, n - n0, tostring(h0 ~= batsum())))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
