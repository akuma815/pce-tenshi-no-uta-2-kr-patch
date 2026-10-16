-- Z11 — 부팅부터 BXR(#7)/BYR(#8) 포착
--  지상검증으로 확정된 정답: 화면원점 = BAT 픽셀 (352, 82)
--  이 값이 씬 진입 시 VDC 에 실제로 기록되는지, 언제 기록되는지 확인한다.
--  ※ 지금까지 프로브는 전부 세이브스테이트 로드 이후부터 감시해 이미 지나간
--    쓰기를 놓쳤다. 그래서 부팅부터 본다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local log = assert(io.open(OUTDIR .. "/bxr.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local sel = 0
local selhist = {}
local cur = {}                       -- 레지스터별 lo/hi 누적
local events = 0
local function val_of(v) if type(v)=="number" then return v end return emu.getregister("A") or 0 end

local function note(r)
  local c = cur[r]
  if not c then return end
  local v = (c.lo or 0) + (c.hi or 0) * 256
  if c.last == v then return end
  c.last = v
  events = events + 1
  if events <= 60 then
    say(string.format("  f%-6d  R%d = %d   (lo=%d hi=%d)", emu.framecount(), r, v, c.lo or 0, c.hi or 0))
  end
end

event.on_bus_write(function(_, v)
  sel = val_of(v) % 32
  selhist[sel] = (selhist[sel] or 0) + 1
end, 0x0000, "sel", "System Bus")

event.on_bus_write(function(_, v)
  if sel == 7 or sel == 8 then
    cur[sel] = cur[sel] or {}
    cur[sel].lo = val_of(v)
  end
end, 0x0002, "lo", "System Bus")

event.on_bus_write(function(_, v)
  if sel == 7 or sel == 8 then
    cur[sel] = cur[sel] or {}
    cur[sel].hi = val_of(v)
    note(sel)
  end
end, 0x0003, "hi", "System Bus")

pcall(client.speedmode, 400)
pcall(client.setscreenshotosd, false)
say("부팅부터 BXR/BYR 감시 시작")

for f = 1, 3600 do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, B1 = true, B2 = true }, 1) end
  emu.frameadvance()
  if f % 400 == 0 then
    pcall(client.screenshot, string.format("%s/bxr_f%05d.png", OUTDIR, f))
    local ks = {}
    for k in pairs(selhist) do ks[#ks+1] = k end
    table.sort(ks)
    local p = {}
    for _, k in ipairs(ks) do p[#p+1] = string.format("R%d:%d", k, selhist[k]) end
    say(string.format("f%d  분포: %s", f, table.concat(p, " ")))
    for _, r in ipairs({7, 8}) do
      local c = cur[r]
      if c then say(string.format("     현재 R%d = %d", r, (c.lo or 0) + (c.hi or 0) * 256)) end
    end
  end
end

say("")
say("=== 최종 ===")
local ks = {}
for k in pairs(selhist) do ks[#ks+1] = k end
table.sort(ks)
local p = {}
for _, k in ipairs(ks) do p[#p+1] = string.format("R%d:%d", k, selhist[k]) end
say("레지스터 선택 분포: " .. table.concat(p, "  "))
for _, r in ipairs({7, 8, 9, 13}) do
  local c = cur[r]
  if c then
    say(string.format("R%d 최종값 = %d", r, (c.lo or 0) + (c.hi or 0) * 256))
  else
    say(string.format("R%d = 미관측", r))
  end
end
say("총 스크롤 변경 이벤트 = " .. events)
log:close()
if client.exit then pcall(client.exit) end
