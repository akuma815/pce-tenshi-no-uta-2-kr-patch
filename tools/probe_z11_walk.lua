-- Z11 진단 — 자유 이동 중 VDC 레지스터 선택 관측
--  목적: 걸어다닐 때 BXR(#7)/BYR(#8)/MWR(#9) 이 쓰이는가?
--        쓰인다 = 스크롤 레지스터 방식 -> 보정식 확보 가능
--        안 쓰인다 = BAT 재작성 방식 -> 런타임 좌표 산출 경로 없음
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local log = assert(io.open(OUTDIR .. "/walk.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

local sel = 0
local selhist = {}
local reg = {}                      -- 레지스터별 마지막 값
local function val_of(v) if type(v)=="number" then return v end return emu.getregister("A") or 0 end

event.on_bus_write(function(_, v)
  sel = val_of(v) % 32
  selhist[sel] = (selhist[sel] or 0) + 1
end, 0x0000, "sel", "System Bus")
event.on_bus_write(function(_, v)
  local r = reg[sel] or {lo=0, hi=0}
  r.lo = val_of(v); reg[sel] = r
end, 0x0002, "lo", "System Bus")
event.on_bus_write(function(_, v)
  local r = reg[sel] or {lo=0, hi=0}
  r.hi = val_of(v); reg[sel] = r
end, 0x0003, "hi", "System Bus")

local function dump(tag)
  local ks = {}
  for k in pairs(selhist) do ks[#ks+1] = k end
  table.sort(ks)
  local p = {}
  for _, k in ipairs(ks) do p[#p+1] = string.format("R%d:%d", k, selhist[k]) end
  say(tag .. " 레지스터 분포: " .. table.concat(p, "  "))
  for _, k in ipairs({7, 8, 9, 5}) do
    local r = reg[k]
    if r then
      say(string.format("   R%d = lo %d hi %d -> %d", k, r.lo, r.hi, r.lo + r.hi*256))
    end
  end
end

pcall(client.setscreenshotosd, false)
pcall(client.speedmode, 100)

-- 1단계: 대사 닫기 (B1 반복)
say("== 1단계: 대사 닫기 ==")
for f = 1, 600 do
  pcall(joypad.set, { B1 = (f % 40 < 20) }, 1)
  emu.frameadvance()
end
pcall(client.screenshot, OUTDIR .. "/walk_after_close.png")
dump("대사닫기후")

-- 2단계: 걸어다니기 (방향키 순환)
say("== 2단계: 이동 ==")
selhist = {}
local dirs = { "Right", "Down", "Left", "Up" }
for f = 1, 1600 do
  local d = dirs[(math.floor(f / 200) % 4) + 1]
  local t = {}
  t[d] = true
  pcall(joypad.set, t, 1)
  emu.frameadvance()
  if f % 400 == 0 then
    pcall(client.screenshot, string.format("%s/walk_%04d.png", OUTDIR, f))
    dump(string.format("f%d(%s)", f, d))
  end
end
dump("최종")
log:close()
if client.exit then pcall(client.exit) end
