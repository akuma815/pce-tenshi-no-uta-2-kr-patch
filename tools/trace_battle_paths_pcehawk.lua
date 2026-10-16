-- 전투 메시지 바이트 경로 추적 (PCEHawk + 원본 디스크 + 원본 카드 + 사용자 세이브 이어하기)
--   글자(GETFNT $967E)마다 직전 글자 이후 $4036(벡터)·$4284(디스패처)·경로 본체(②$42AB ③$42DE ④$4291) 히트 수와
--   zp 52/53/54/55, MPR6 을 기록 → 배틀 프린터가 어느 경로로 바이트를 얻는지 확정.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b19_runtime]]
local BUS = "System Bus"
local log = assert(io.open(OUTDIR .. "/battle_paths.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, BUS) end
local function z(a) return rd(0x2000 + a) end
local function reg(n) return emu.getregister(n) or -1 end
local c = { v=0, d=0, p2=0, p3=0, p4=0 }
event.on_bus_exec(function() c.v = c.v + 1 end, 0x4036, "vec", BUS)
event.on_bus_exec(function() c.d = c.d + 1 end, 0x4284, "disp", BUS)
event.on_bus_exec(function() c.p2 = c.p2 + 1 end, 0x42AB, "p2", BUS)
event.on_bus_exec(function() c.p3 = c.p3 + 1 end, 0x42DE, "p3", BUS)
event.on_bus_exec(function() c.p4 = c.p4 + 1 end, 0x4291, "p4", BUS)
local nchar, burst, last = 0, {}, -1000
event.on_bus_exec(function()
  nchar = nchar + 1
  local ch = string.format("%02X%02X", z(0xF9), z(0xF8))
  burst[#burst+1] = string.format("%s[v%d d%d %d/%d/%d]", ch, c.v, c.d, c.p2, c.p3, c.p4)
  c.v, c.d, c.p2, c.p3, c.p4 = 0, 0, 0, 0, 0
  last = emu.framecount()
end, 0x967E, "getfnt", BUS)
say("start")
local shots = 0
for f = 1, 9000 do
  -- 타이틀 통과·이어하기: 300~1800 프레임 Run/B1 펄스. 이후 좌우로 걸으며 전투 유발, 메시지 넘김용 B1.
  if f > 300 and f < 1800 and f % 120 < 3 then pcall(joypad.set, { Run = true, B1 = true }, 1)
  elseif f >= 1800 then
    local ph = (f // 90) % 4
    local pad = {}
    if ph == 0 then pad.Left = true elseif ph == 2 then pad.Right = true end
    if f % 45 == 0 then pad.B1 = true end
    pcall(joypad.set, pad, 1)
  end
  emu.frameadvance()
  if #burst > 0 and emu.framecount() - last >= 12 then
    say(string.format("f%d zp52/53=%02X/%02X 54/55=%02X/%02X 2E69=%02X MPR6=%02X  %s",
      emu.framecount(), z(0x52), z(0x53), z(0x54), z(0x55), rd(0x2E69), reg("MPR-6"), table.concat(burst, " ")))
    burst = {}
    if shots < 12 then shots = shots + 1; pcall(client.screenshot, string.format("%s/bp_%02d_f%05d.png", OUTDIR, shots, emu.framecount())) end
  end
  if f % 1500 == 0 then pcall(client.screenshot, string.format("%s/bp_walk_f%05d.png", OUTDIR, f)) end
end
say("done chars=" .. nchar)
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
