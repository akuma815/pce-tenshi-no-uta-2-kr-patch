-- PCEHawk + 원본 디스크 QuickSave5(카드 결과 화면): N 선택 → 필드 복귀 동안의 $E009 CD 읽기(lba/cnt/mode) 전부 기록
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUT .. "/cardexit_reads.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, BUS) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local armed, f0 = false, 0
event.on_bus_exec(function()
  if not armed then return end
  local z = {}
  for a = 0xF8, 0xFF do z[#z+1] = string.format("%02X", rd(0x2000 + a)) end
  local s = reg("S"); local ret = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256
  local rets = {}
  for k = 1, 8 do rets[#rets+1] = string.format("%04X", rd(0x2100 + ((s + 2*k - 1) % 256)) + rd(0x2100 + ((s + 2*k) % 256)) * 256) end
  say("  retchain=" .. table.concat(rets, ","))
  local f = assert(io.open(OUT .. string.format("/exit_ram23_%d.bin", emu.framecount() - f0), "wb")); local t = {}
  for a = 0x2100, 0x24FF do t[#t+1] = string.char(rd(a)) end
  f:write(table.concat(t)); f:close()
  local f2 = assert(io.open(OUT .. string.format("/exit_ram3f_%d.bin", emu.framecount() - f0), "wb")); local t2 = {}
  for a = 0x3F00, 0x3FFF do t2[#t2+1] = string.char(rd(a)) end
  f2:write(table.concat(t2)); f2:close()
  say(string.format("S=%02X", s))
  say(string.format("f%d E009 lba=%d cnt=%d mode=%02X zpF8..FF=%s ret=%04X m2=%02X m3=%02X m4=%02X m5=%02X m6=%02X", emu.framecount() - f0, rd(0x20FC) * 0x10000 + rd(0x20FD) * 0x100 + rd(0x20FE), rd(0x20F8), rd(0x20FF), table.concat(z, " "), ret, reg("MPR-2"), reg("MPR-3"), reg("MPR-4"), reg("MPR-5"), reg("MPR-6")))
end, 0xE009, "cdread", BUS)
pcall(function() client.speedmode(400) end)
for i = 1, 30 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave5.State")
for i = 1, 5 do emu.frameadvance() end
armed = true; f0 = emu.framecount()
local seq = {{"Right", 3}, {nil, 20}, {"B1", 3}, {nil, 600}, {"B1", 3}, {nil, 200}, {"B1", 3}, {nil, 200}, {"B1", 3}, {nil, 200}, {"B1", 3}, {nil, 200}, }
for _, step in ipairs(seq) do
  for f = 1, step[2] do
    if step[1] then pcall(joypad.set, {[step[1]] = true}, 1) end
    emu.frameadvance()
    if (emu.framecount() - f0) % 30 == 0 then pcall(client.screenshot, OUT .. string.format("/orig_exit_%04d.png", emu.framecount() - f0)) end
  end
  say(string.format("f%d step %s done", emu.framecount() - f0, tostring(step[1])))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
