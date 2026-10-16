-- PCEHawk + 원본 디스크 QuickSave1(도박사 앞): B1 연타로 대화 → 「참가」 선택 → 카드 모듈 로드까지의 $E009 읽기 전부(zp $F8-$FF 전체 + MPR) 기록
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUT .. "/cardenter_reads.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, BUS) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local armed, f0 = false, 0
event.on_bus_exec(function()
  if not armed then return end
  local z = {}
  for a = 0xF8, 0xFF do z[#z+1] = string.format("%02X", rd(0x2000 + a)) end
  local s = reg("S"); local ret = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256
  say(string.format("f%d E009 lba=%d cnt=%d mode=%02X zpF8..FF=%s ret=%04X m2=%02X m3=%02X m4=%02X m5=%02X m6=%02X", emu.framecount() - f0,
    rd(0x20FC) * 0x10000 + rd(0x20FD) * 0x100 + rd(0x20FE), rd(0x20F8), rd(0x20FF), table.concat(z, " "), ret, reg("MPR-2"), reg("MPR-3"), reg("MPR-4"), reg("MPR-5"), reg("MPR-6")))
end, 0xE009, "cdread", BUS)
pcall(function() client.speedmode(400) end)
for i = 1, 30 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave1.State")
for i = 1, 5 do emu.frameadvance() end
armed = true; f0 = emu.framecount()
for i = 1, 12 do
  for f = 1, 3 do pcall(joypad.set, {B1 = true}, 1); emu.frameadvance() end
  for f = 1, 150 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/enter_%02d.png", i))
  say(string.format("f%d press %d", emu.framecount() - f0, i))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
