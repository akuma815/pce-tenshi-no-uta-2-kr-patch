-- Z11.5 — 창 영역 한정 + 타일 매칭 (실패 #3 을 실패 #4 로 감싼 합성)
--  확정 사실:
--   1) BXR/BYR/MWR 은 게임 전체에서 미사용 -> BAT 셀 -> 화면은 직접 대응(x=c*8, y=r*8)
--   2) 대사창의 BAT 셀은 고정이다. 글자는 그 셀이 가리키는 타일 패턴을 덮어써서 나타난다
--      (창 영역 BAT diff = 0 셀로 실증)
--  따라서: 창 영역 안에서 "이번 버스트에 패턴이 쓰인 타일"을 가리키는 셀 = 글자 자리
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local CSV    = OUTDIR .. "/overlay_poc.csv"
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local QUIET, VR = 8, "VRAM1"
local BAT_COLS = 64
local WIN = { r0 = 16, r1 = 27, c0 = 1, c1 = 43 }   -- 대사창 영역(정적 추출값에 여유)

local log = assert(io.open(OUTDIR .. "/z11_5.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local KO = {}
do
  local n, f = 0, io.open(CSV, "r")
  if f then
    f:read("*l")
    for line in f:lines() do
      local k, _, v = line:match("^([^\t]*)\t([^\t]*)\t(.*)$")
      if k and v and #k > 0 then
        local t = {}
        for x in (v .. "|"):gmatch("([^|]*)|") do t[#t+1] = x end
        KO[k] = t; n = n + 1
      end
    end
    f:close()
  end
  say("번역표 " .. n .. "건")
end

local function vb(a) return memory.read_u8(a, VR) end
local function pal_rgb(p, i)
  local e = (p*16 + i) * 2
  local ok, lo = pcall(memory.read_u8, e, "VCEPalette")
  local ok2, hi = pcall(memory.read_u8, e+1, "VCEPalette")
  if not (ok and ok2) then return nil end
  local v = lo + hi*256
  local B, R, G = v % 8, math.floor(v/8) % 8, math.floor(v/64) % 8
  local function s(x) return math.floor(x*255/7) end
  return 0xFF000000 + s(R)*0x10000 + s(G)*0x100 + s(B), R, G, B
end
local function tile_pixel(t, x, y)
  local b, m = t*32, 2 ^ (7-x)
  local function bit(p) return math.floor(p/m) % 2 end
  return bit(vb(b+y*2)) + bit(vb(b+y*2+1))*2 + bit(vb(b+16+y*2))*4 + bit(vb(b+16+y*2+1))*8
end

local chars, nhit, last_hit, show = {}, 0, -10000, nil
local sel, mawr_lo, mawr = 0, 0, 0
local tiles = {}
local function val_of(v) if type(v)=="number" then return v end return emu.getregister("A") or 0 end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

event.on_bus_write(function(_, v) sel = val_of(v) % 32 end, 0x0000, "sel", "System Bus")
event.on_bus_write(function(_, v) if sel == 0 then mawr_lo = val_of(v) end end, 0x0002, "lo", "System Bus")
event.on_bus_write(function(_, v)
  local x = val_of(v)
  if sel == 0 then
    mawr = mawr_lo + x * 256
  elseif sel == 2 then
    if mawr >= 0x800 then tiles[math.floor(mawr / 16)] = true end
    mawr = (mawr + 1) % 0x8000
  end
end, 0x0003, "hi", "System Bus")

event.on_bus_exec(function()
  local fc = emu.framecount()
  if nhit == 0 or (fc - last_hit) >= QUIET then chars = {}; tiles = {} end
  nhit = nhit + 1; last_hit = fc
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "chr", "System Bus")

-- 창 영역 안에서 "쓰인 타일"을 가리키는 셀
local function text_cells()
  local out = {}
  for r = WIN.r0, WIN.r1 do
    for c = WIN.c0, WIN.c1 do
      local a = (r * BAT_COLS + c) * 2
      local e = vb(a) + vb(a+1) * 256
      if tiles[e % 4096] then out[#out+1] = { r = r, c = c } end
    end
  end
  return out
end

local function to_segments(cells)
  local perrow = {}
  for _, h in ipairs(cells) do perrow[h.r] = perrow[h.r] or {}; table.insert(perrow[h.r], h.c) end
  local runs = {}
  for r, cols in pairs(perrow) do
    table.sort(cols)
    local s, p = cols[1], cols[1]
    for i = 2, #cols do
      if cols[i] - p > 2 then runs[#runs+1] = {r=r, c0=s, c1=p, h=1}; s = cols[i] end
      p = cols[i]
    end
    runs[#runs+1] = {r=r, c0=s, c1=p, h=1}
  end
  table.sort(runs, function(x,y) if x.r~=y.r then return x.r<y.r end return x.c0<y.c0 end)
  local out, used = {}, {}
  for i, q in ipairs(runs) do
    if not used[i] then
      local seg = {r=q.r, c0=q.c0, c1=q.c1, h=1}
      for j = i+1, #runs do
        local w = runs[j]
        if not used[j] and seg.h < 2 and w.r == seg.r + seg.h
           and w.c0 <= seg.c1 + 1 and w.c1 >= seg.c0 - 1 then
          seg.c0 = math.min(seg.c0, w.c0); seg.c1 = math.max(seg.c1, w.c1)
          seg.h = seg.h + 1; used[j] = true
        end
      end
      out[#out+1] = seg
    end
  end
  table.sort(out, function(x,y) if x.r~=y.r then return x.r<y.r end return x.c0<y.c0 end)
  return out
end

local function window_color(segs)
  for _, q in ipairs(segs) do
    local c = (q.c0 > WIN.c0) and (q.c0 - 1) or (q.c1 + 1)
    if c >= 0 and c < BAT_COLS then
      local a = (q.r * BAT_COLS + c) * 2
      local e = vb(a) + vb(a+1) * 256
      local rgb, R, G, B = pal_rgb(math.floor(e/4096), tile_pixel(e % 4096, 4, 4))
      if rgb then return rgb, string.format("pal=%d GRB=%d,%d,%d", math.floor(e/4096), G, R, B) end
    end
  end
  return 0xFF000000, "fallback"
end

local function draw()
  pcall(gui.use_surface, "emucore")
  if not show then return end
  local PAD = 6
  for _, q in ipairs(show.segs) do
    local x, y = q.c0*8 - PAD, q.r*8 - PAD
    local w, h = (q.c1-q.c0+1)*8 + PAD*2, q.h*8 + PAD*2
    if x < 0 then w = w + x; x = 0 end
    if y < 0 then h = h + y; y = 0 end
    pcall(gui.drawRectangle, x, y, w, h, show.color, show.color)
  end
  for i, q in ipairs(show.segs) do
    local t = show.text[i]
    if t and #t > 0 then
      pcall(gui.drawText, q.c0*8, q.r*8 - 1, t, 0xFFFFFFFF, show.color, 12, "Malgun Gothic")
    end
  end
end

pcall(client.setscreenshotosd, true)
pcall(gui.use_surface, "emucore")
pcall(client.speedmode, 100)
say(string.format("Z11.5 가동  창영역 행%d..%d 칼럼%d..%d", WIN.r0, WIN.r1, WIN.c0, WIN.c1))

local shots, seen = 0, 0
for f = 1, 2400 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  if nhit > 0 and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    seen = seen + 1
    local key = table.concat(chars, "")
    local ko  = KO[key]
    local nt = 0; for _ in pairs(tiles) do nt = nt + 1 end
    local cells = text_cells()
    local segs = to_segments(cells)
    say(string.format("BURST %d  %d글자  타일%d  셀%d  세그%d  match=%s",
        seen, #chars, nt, #cells, #segs, ko and "YES" or "no"))
    for i = 1, math.min(#segs, 8) do
      local q = segs[i]
      say(string.format("    seg%d 행%d..%d 칼럼%d..%d  px=(%d,%d)",
          i, q.r, q.r+q.h-1, q.c0, q.c1, q.c0*8, q.r*8))
    end
    if ko and #segs > 0 then
      local col, dbg = window_color(segs)
      show = { segs = segs, color = col, text = ko }
      say("  HIT 색=" .. string.format("%08X ", col) .. dbg)
      for i = 1, 12 do draw(); emu.frameadvance() end
      shots = shots + 1
      pcall(client.screenshot, string.format("%s/z11_5_%02d.png", OUTDIR, shots))
      if shots >= 2 then break end
    end
    chars = {}; tiles = {}
  end
  draw()
  emu.frameadvance()
end
say(string.format("done bursts=%d shots=%d", seen, shots))
log:close()
if client.exit then pcall(client.exit) end
