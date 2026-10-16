-- b13 2차: 디스패처 $4284 의 세 스트림 본체에 훅을 걸어, 버스트마다
--   어느 경로 / 어느 뱅크 / 어느 물리 주소에서 원문을 읽는지 기록한다.
--   ② $42AB  LDA ($52)            — $53 스트림 (메모)
--   ③ $42DE  LDA ($4B)  (MPR6 = $22D0 + $2E69 로 스왑된 상태) — 초상화 대사 (1차 실측)
--   ④ 기본   $4291.. LDA ($4B)     — 정확한 LDA 주소는 1차에서 못 봤으므로 $4291 진입만 기록
-- 출력: translation/b13_fetch_trace/paths.tsv (read 1건 = 1행, 버스트 단위 요약은 log)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b13_fetch_trace]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local BUS    = "System Bus"
local log = assert(io.open(OUTDIR .. "/paths.log", "w"))
local tsv = assert(io.open(OUTDIR .. "/paths.tsv", "w"))
tsv:write("frame\tpath\tlogical\tbank\tphys\tval\tv22D0\tv2E69\n")
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, BUS) end
local function z(a) return rd(0x2000 + a) end
local function reg(n) return emu.getregister(n) or -1 end

local n = { [2]=0, [3]=0, [4]=0 }
local firsts = {}
local function rec(path, ptr_lo, ptr_hi)
  local lo, hi = z(ptr_lo), z(ptr_hi)
  local la = lo + hi * 256
  local bank = reg("MPR-" .. math.floor(la / 0x2000))
  local ph = bank * 0x2000 + (la % 0x2000)
  local v = rd(la)
  n[path] = n[path] + 1
  tsv:write(string.format("%d\t%d\t%04X\t%02X\t%06X\t%02X\t%02X\t%02X\n",
    emu.framecount(), path, la, bank, ph, v, rd(0x22D0), rd(0x2E69)))
  if n[path] <= 3 or (n[path] % 50 == 0) then
    say(string.format("f%d path%d #%d  logical=%04X bank=%02X phys=%06X val=%02X  $22D0=%02X $2E69=%02X MPR=[%02X %02X %02X %02X %02X %02X %02X %02X]",
      emu.framecount(), path, n[path], la, bank, ph, v, rd(0x22D0), rd(0x2E69),
      reg("MPR-0"), reg("MPR-1"), reg("MPR-2"), reg("MPR-3"), reg("MPR-4"), reg("MPR-5"), reg("MPR-6"), reg("MPR-7")))
  end
end
event.on_bus_exec(function() rec(2, 0x52, 0x53) end, 0x42AB, "b13 p2", BUS)
event.on_bus_exec(function() rec(3, 0x4B, 0x4C) end, 0x42DE, "b13 p3", BUS)
event.on_bus_exec(function()
  n[4] = n[4] + 1
  if n[4] <= 3 then
    say(string.format("f%d path4(기본) 진입 #%d  4B/4C=%02X/%02X MPR6=%02X", emu.framecount(), n[4], z(0x4B), z(0x4C), reg("MPR-6")))
    -- 기본 경로 본체를 8줄 역어셈블해 LDA 주소를 확정
    local pc = 0x4291
    for i = 1, 10 do
      local ok, d = pcall(emu.disassemble, pc, BUS)
      if not ok or type(d) ~= "table" then break end
      say(string.format("    %04X  %s", pc, d.disasm)); pc = pc + (d.length or 1)
    end
  end
end, 0x4291, "b13 p4", BUS)

-- 글자 수집 (버스트 경계용)
local chars, last_hit = 0, -1000
event.on_bus_exec(function() chars = chars + 1; last_hit = emu.framecount() end, 0x967E, "b13 getfnt", BUS)

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
local f0, idle, lastc = emu.framecount(), 0, 0
while true do
  local f = emu.framecount() - f0
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  emu.frameadvance()
  if chars ~= lastc then lastc = chars; idle = 0 else idle = idle + 1 end
  if (chars > 0 and idle >= 120) or f > 900 then break end
end
say(string.format("done chars=%d path2=%d path3=%d path4=%d", chars, n[2], n[3], n[4]))
log:close(); tsv:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
