-- Z11 — 글자별 BAT 셀을 diff 없이 직접 포착
-- 원리: $967E(글자 렌더) 직후 게임이 그 글자의 BAT 엔트리를 쓴다.
--       MAWR(R0)= VRAM 워드주소. BAT 워드주소 = 행*64 + 칼럼 (< 0x800).
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local log = assert(io.open(OUTDIR .. "/mawr.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

local sel, mawr_lo, mawr = 0, 0, 0
local armed, rows = false, {}
local nchar = 0
local function val_of(v) if type(v)=="number" then return v end return emu.getregister("A") or 0 end

event.on_bus_write(function(_, v) sel = val_of(v) % 32 end, 0x0000, "sel", "System Bus")
event.on_bus_write(function(_, v) if sel == 0 then mawr_lo = val_of(v) end end, 0x0002, "lo", "System Bus")
event.on_bus_write(function(_, v)
  if sel ~= 0 then return end
  mawr = mawr_lo + val_of(v) * 256
  if armed and mawr < 0x800 then                 -- BAT 범위 워드주소
    local r, c = math.floor(mawr / 64), mawr % 64
    rows[#rows+1] = { n = nchar, r = r, c = c, a = mawr }
    armed = false
  end
end, 0x0003, "hi", "System Bus")

event.on_bus_exec(function()
  nchar = nchar + 1
  armed = true                                    -- 다음 BAT 주소 설정이 이 글자의 셀
end, 0x967E, "chr", "System Bus")

pcall(client.speedmode, 100)
pcall(client.setscreenshotosd, false)
for f = 1, 900 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  emu.frameadvance()
  if f == 450 then pcall(client.screenshot, OUTDIR .. "/mawr_mid.png") end
end

say(string.format("글자 %d개 / BAT 셀 포착 %d개", nchar, #rows))
local rmin, rmax, cmin, cmax = 99, -1, 99, -1
for _, q in ipairs(rows) do
  if q.r < rmin then rmin = q.r end
  if q.r > rmax then rmax = q.r end
  if q.c < cmin then cmin = q.c end
  if q.c > cmax then cmax = q.c end
end
say(string.format("셀 범위: 행 %d..%d  칼럼 %d..%d   -> 픽셀 x=%d..%d y=%d..%d",
    rmin, rmax, cmin, cmax, cmin*8, cmax*8+7, rmin*8, rmax*8+7))
say("처음 24개:")
for i = 1, math.min(24, #rows) do
  local q = rows[i]
  say(string.format("  #%d  addr=$%04X  행%2d 칼럼%2d  px=(%3d,%3d)", q.n, q.a, q.r, q.c, q.c*8, q.r*8))
end
log:close()
if client.exit then pcall(client.exit) end
