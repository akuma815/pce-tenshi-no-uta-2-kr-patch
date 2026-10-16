-- Z11 스크롤 추적 프로브 — VDC 포트 쓰기로 BXR(#7)/BYR(#8) 을 그림자 유지
-- 목표: 버스트 검출 셀 좌표를 스크롤 보정해 실제 창 위치와 대조
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local BAT_STRIDE, BAT_SCAN, QUIET, VR = 0x80, 0x1000, 8, "VRAM1"

local log = assert(io.open(OUTDIR .. "/scroll.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local before, chars, nhit, last_hit = nil, {}, 0, -10000
local sel, BXR, BYR = 0, 0, 0
local dbg_w = 0

local function snap() local ok,a = pcall(memory.read_bytes_as_array, 0, BAT_SCAN, VR); return ok and a or nil end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

-- ---------- VDC 포트 쓰기 훅 ----------
local function val_of(v)
  if type(v) == "number" then return v end
  return emu.getregister("A") or 0        -- 파라미터 미전달 시 6502 STA 의 A 로 대체
end

event.on_bus_write(function(addr, v)
  dbg_w = dbg_w + 1
  if dbg_w <= 6 then
    say(string.format("  W$0000 addr=%s val=%s (A=%02X)", tostring(addr), tostring(v),
        emu.getregister("A") or 0))
  end
  sel = val_of(v) % 32
end, 0x0000, "vdc sel", "System Bus")

event.on_bus_write(function(addr, v)
  local x = val_of(v)
  if sel == 7 then BXR = (BXR - BXR % 256) + x
  elseif sel == 8 then BYR = (BYR - BYR % 256) + x end
end, 0x0002, "vdc lo", "System Bus")

event.on_bus_write(function(addr, v)
  local x = val_of(v)
  if sel == 7 then BXR = (BXR % 256) + x * 256
  elseif sel == 8 then BYR = (BYR % 256) + x * 256 end
end, 0x0003, "vdc hi", "System Bus")

event.on_bus_exec(function()
  local fc = emu.framecount()
  if nhit == 0 or (fc - last_hit) >= QUIET then before = snap(); chars = {} end
  nhit = nhit + 1; last_hit = fc
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "z11 scroll", "System Bus")

pcall(client.setscreenshotosd, false)
pcall(client.speedmode, 100)
say("스크롤 추적 시작")

local seen = 0
for f = 1, 2400 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  if f % 400 == 0 then say(string.format("  tick f=%d BXR=%d(%d셀) BYR=%d(%d셀) nhit=%d",
      f, BXR, math.floor(BXR/8), BYR, math.floor(BYR/8), nhit)) end
  if nhit > 0 and before and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    seen = seen + 1
    local after = snap()
    -- 변경 셀 범위
    local rmin, rmax, cmin, cmax = 99, -1, 99, -1
    if before and after then
      for i = 1, BAT_SCAN, 2 do
        if before[i] ~= after[i] or before[i+1] ~= after[i+1] then
          local off = i-1
          local r, c = math.floor(off/BAT_STRIDE), math.floor((off%BAT_STRIDE)/2)
          if r < rmin then rmin = r end
          if r > rmax then rmax = r end
          if c < cmin then cmin = c end
          if c > cmax then cmax = c end
        end
      end
    end
    local bx, by = math.floor(BXR/8), math.floor(BYR/8)
    say(string.format("BURST %d  %d글자  BAT 행%d..%d 칼럼%d..%d  BXR=%d(%d셀) BYR=%d(%d셀)",
        seen, #chars, rmin, rmax, cmin, cmax, BXR, bx, BYR, by))
    say(string.format("      보정 화면칼럼 %d..%d   화면행 %d..%d   px=(%d,%d)",
        (cmin-bx) % 64, (cmax-bx) % 64, (rmin-by) % 32, (rmax-by) % 32,
        ((cmin-bx) % 64)*8, ((rmin-by) % 32)*8))
    if seen <= 3 then pcall(client.screenshot, string.format("%s/scroll_%02d.png", OUTDIR, seen)) end
    before = nil; chars = {}
    if seen >= 6 then break end
  end
  emu.frameadvance()
end
say("done bursts=" .. seen .. " nhit=" .. nhit)
log:close()
if client.exit then pcall(client.exit) end
