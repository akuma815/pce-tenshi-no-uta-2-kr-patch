-- PCEHawk(원본 디스크) + 사용자 s1 스테이트(도박사 앞): B1 로 말 걸기 → 디스패처($4284) 호출 로그(복귀주소·MPR6·zp52~55·반환 바이트) + 스크린샷
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUT .. "/gambler.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, BUS) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local armed, n, dumped = false, 0, false
event.on_bus_exec(function()
  if not armed or n > 1500 then return end
  n = n + 1
  local s = reg("S"); local ret = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256
  local ret0 = ret
  if ret0 == 0x92F0 and not dumped then
    dumped = true
    local f = assert(io.open(OUT .. "/gambler_bus21.bin", "wb"))
    local dom = "System Bus (21 bit)"; local size = memory.getmemorydomainsize(dom)
    for a = 0, size - 1, 4096 do
      local nn = math.min(4096, size - a); local bb = memory.read_bytes_as_array(a, nn, dom); local t = {}
      for i = 1, nn do t[i] = string.char(bb[i]) end
      f:write(table.concat(t))
    end
    f:close()
    say("bus21 size=" .. size .. string.format(" mpr0=%02X mpr1=%02X mpr7=%02X", reg("MPR-0"), reg("MPR-1"), reg("MPR-7")))
    say(string.format("DUMP mpr5=%02X mpr4=%02X mpr3=%02X mpr2=%02X", reg("MPR-5"), reg("MPR-4"), reg("MPR-3"), reg("MPR-2")))
  end
  say(string.format("f%d disp ret=%04X m5=%02X m6=%02X 2E69=%02X zp52=%02X 53=%02X 54=%02X 55=%02X 4B=%02X 4C=%02X", emu.framecount(), ret, reg("MPR-5"), reg("MPR-6"), rd(0x2E69), rd(0x2052), rd(0x2053), rd(0x2054), rd(0x2055), rd(0x204B), rd(0x204C)))
end, 0x4284, "disp", BUS)
event.on_bus_exec(function()
  if not armed then return end
  say(string.format("f%d E009 read lba=%d cnt=%d mode=%02X", emu.framecount(), rd(0x20FC) * 0x10000 + rd(0x20FD) * 0x100 + rd(0x20FE), rd(0x20F8), rd(0x20FF)))
end, 0xE009, "cdread", BUS)
pcall(function() client.speedmode(400) end)
for i = 1, 30 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave1.State")
for i = 1, 5 do emu.frameadvance() end
armed = true
pcall(client.screenshot, OUT .. "/gambler_0.png")
for i = 1, 4 do
  for f = 1, 3 do pcall(joypad.set, {B1 = true}, 1); emu.frameadvance() end
  for f = 1, 120 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/gambler_%d.png", i))
  say("press " .. i .. " done, calls=" .. n)
end
-- 디스패처가 읽는 스트림 근처 RAM 덤프 (zp52/53 포인터)
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
