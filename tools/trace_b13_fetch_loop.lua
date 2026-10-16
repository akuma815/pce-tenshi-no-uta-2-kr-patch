-- b13: 초상화 대사 페치 루프 역추적 (PCEHawk + diag_portrait_pcehawk.State)
--
-- 목적: 초상화 대사 글자가 $967E(GETFNT) 로 가기 직전, 누가 원문 바이트를 어디서
--       읽어 zp $F8/$F9 에 쓰는지 잡는다. armchk 미진입(HANDOFF §6)은 부정적 증거였고
--       루프의 코드 위치는 아직 아무도 본 적 없다.
-- 방법: 상태 로드 → B1 로 대사 진행 → (무장 구간 동안) 전 명령 PC 링버퍼 + 전 read
--       링버퍼 → zp $F9 쓰기 시점에 링버퍼·레지스터·zp 전체·역어셈블을 덤프.
--       3글자 잡으면 무거운 훅 해제, 버스트 끝까지 글자만 수집 후 종료.
-- 주의: 콜백 주소는 16비트 논리 주소(HuC6280.ReadMemory, "System Bus"). zp = $2000+n.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b13_fetch_trace]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local BUS    = "System Bus"

local log = assert(io.open(OUTDIR .. "/trace.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, BUS) end
local function z(a) return rd(0x2000 + a) end
local function reg(n) return emu.getregister(n) or -1 end
local function mprs()
  local t = {}
  for i = 0, 7 do t[#t+1] = string.format("%02X", reg("MPR-" .. i)) end
  return table.concat(t, " ")
end
-- 논리 → 물리(21bit)
local function phys(a) return reg("MPR-" .. math.floor(a / 0x2000)) * 0x2000 + (a % 0x2000) end

local function zp_dump(tag)
  say("ZP " .. tag)
  for row = 0, 15 do
    local t = {}
    for i = 0, 15 do t[#t+1] = string.format("%02X", z(row*16 + i)) end
    say(string.format("  %02X: %s", row*16, table.concat(t, " ")))
  end
end

-- 링버퍼
local RING = 96
local pcs, pci = {}, 0          -- 명령 PC
local rds, rdi = {}, 0          -- (addr, val, pc)
local armed, hits, chars = false, 0, {}
local ids = {}

local function dump_rings(tag)
  say("---- " .. tag .. "  frame=" .. emu.framecount())
  say(string.format("  PC=%04X A=%02X X=%02X Y=%02X S=%02X  MPR=[%s]",
    reg("PC"), reg("A"), reg("X"), reg("Y"), reg("S"), mprs()))
  -- 최근 명령 (오래된 것부터)
  say("  최근 명령:")
  local n = math.min(#pcs, RING)
  for k = n, 1, -1 do
    local idx = ((pci - k) % RING) + 1
    local pc = pcs[idx]
    if pc then
      local ok, d = pcall(emu.disassemble, pc, BUS)
      local txt = (ok and type(d) == "table" and d.disasm) or (ok and tostring(d)) or "?"
      say(string.format("    %04X [%06X]  %s", pc, phys(pc), txt))
    end
  end
  say("  최근 read (addr val pc):")
  local m = math.min(#rds, 48)
  for k = m, 1, -1 do
    local idx = ((rdi - k) % RING) + 1
    local r = rds[idx]
    if r then say(string.format("    %04X [%06X] = %02X   @PC %04X", r[1], phys(r[1]), r[2], r[3])) end
  end
end

local function unarm()
  if not armed then return end
  armed = false
  for _, id in ipairs(ids) do pcall(event.unregisterbyid, id) end
  ids = {}
  say("무거운 훅 해제 (hits=" .. hits .. ")")
end

local function arm()
  if armed then return end
  armed = true
  ids[#ids+1] = event.on_bus_exec_any(function(addr)
    pci = (pci % RING) + 1; pcs[pci] = addr
  end, "b13 exec", BUS)
  ids[#ids+1] = event.on_bus_read(function(addr, val)
    rdi = (rdi % RING) + 1; rds[rdi] = { addr, val, reg("PC") }
  end, nil, "b13 read", BUS)
  ids[#ids+1] = event.on_bus_write(function(addr, val)
    hits = hits + 1
    say(string.format("== zp $F9 쓰기 #%d  val=%02X (F8=%02X)", hits, val, z(0xF8)))
    dump_rings("F9 write #" .. hits)
    if hits == 1 then zp_dump("at F9 write #1") end
    if hits == 3 then zp_dump("at F9 write #3"); unarm() end
  end, 0x20F9, "b13 f9w", BUS)
  say("무장: exec_any + read_any + write $20F9")
end

-- 렌더 초크포인트: 글자 수집 + 호출자
event.on_bus_exec(function()
  local s = reg("S")
  local lo, hi = rd(0x2100 + ((s + 1) % 256)), rd(0x2100 + ((s + 2) % 256))
  local ret = lo + hi * 256 + 1
  local ch = string.format("%02X%02X", z(0xF9), z(0xF8))
  chars[#chars+1] = ch
  if #chars <= 40 then
    say(string.format("GETFNT #%d f%d ch=%s caller=%04X [%06X] zp52/53=%02X/%02X 54/55=%02X/%02X 4B/4C=%02X/%02X MPR=[%s]",
      #chars, emu.framecount(), ch, ret - 3, phys(ret - 3), z(0x52), z(0x53), z(0x54), z(0x55), z(0x4B), z(0x4C), mprs()))
  end
end, 0x967E, "b13 getfnt", BUS)

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUTDIR .. "/t0.png")
zp_dump("after load")
say("MPR after load = " .. mprs())

-- 대사 진행: B1 30프레임 홀드 / 30프레임 해제. 무장은 첫 입력 직전.
arm()
local f0 = emu.framecount()
local last_n, idle = 0, 0
while true do
  local f = emu.framecount() - f0
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  emu.frameadvance()
  if #chars ~= last_n then last_n = #chars; idle = 0 else idle = idle + 1 end
  if f == 120 then pcall(client.screenshot, OUTDIR .. "/t120.png") end
  if (#chars > 0 and idle >= 90) or f > 600 then break end
end
unarm()
pcall(client.screenshot, OUTDIR .. "/t_end.png")
say("chars=" .. #chars .. "  sjis=" .. table.concat(chars, ""))
say("done")
log:close()
client.exitprogram()
