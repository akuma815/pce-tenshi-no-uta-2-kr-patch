-- Z11.4 — 창 영역 한정 BAT diff
--  진단 결과: BXR/BYR/MWR 은 게임 전체에서 한 번도 쓰이지 않는다(이동 중 포함).
--  => BAT 셀 -> 화면 좌표는 직접 대응(x=col*8, y=row*8)이 맞다.
--     문제는 좌표가 아니라 "배경 갱신이 diff 를 오염시키는 것"이었다.
--  해법: 창 영역(정적 추출값) 안으로 diff 를 한정한다. 밖의 배경 변화는 무시.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local CSV    = OUTDIR .. "/overlay_poc.csv"
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local QUIET, VR = 8, "VRAM1"
local BAT_COLS = 64

-- 초상화/일반 대사창 (harvest 정적 추출: 화면 (18,144) 316x60)
local WIN = { r0 = 17, r1 = 26, c0 = 2, c1 = 42 }

local log = assert(io.open(OUTDIR .. "/z11_4.log", "w"))
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

-- 창 영역만 스냅 (행 r0..r1, 칼럼 c0..c1)
local function snap_win()
  local t = {}
  for r = WIN.r0, WIN.r1 do
    for c = WIN.c0, WIN.c1 do
      local a = (r * BAT_COLS + c) * 2
      t[#t+1] = vb(a) + vb(a+1) * 256
    end
  end
  return t
end

local chars, nhit, last_hit, show, before = {}, 0, -10000, nil, nil

event.on_bus_exec(function()
  local fc = emu.framecount()
  if nhit == 0 or (fc - last_hit) >= QUIET then before = snap_win(); chars = {} end
  nhit = nhit + 1; last_hit = fc
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "chr", "System Bus")

local W = WIN.c1 - WIN.c0 + 1
local function changed_cells(a, b)
  local out = {}
  if not a or not b then return out end
  for i = 1, #a do
    if a[i] ~= b[i] then
      local k = i - 1
      out[#out+1] = { r = WIN.r0 + math.floor(k / W), c = WIN.c0 + (k % W) }
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

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

pcall(client.setscreenshotosd, true)
pcall(gui.use_surface, "emucore")
pcall(client.speedmode, 100)
say(string.format("Z11.4 가동  창영역 행%d..%d 칼럼%d..%d", WIN.r0, WIN.r1, WIN.c0, WIN.c1))

local shots, seen = 0, 0
for f = 1, 2400 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  if nhit > 0 and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    seen = seen + 1
    local key = table.concat(chars, "")
    local ko  = KO[key]
    local cells = changed_cells(before, snap_win())
    local segs = to_segments(cells)
    say(string.format("BURST %d  %d글자  셀%d  세그%d  match=%s",
        seen, #chars, #cells, #segs, ko and "YES" or "no"))
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
      pcall(client.screenshot, string.format("%s/z11_4_%02d.png", OUTDIR, shots))
      if shots >= 2 then break end
    end
    before = nil; chars = {}
  end
  draw()
  emu.frameadvance()
end
say(string.format("done bursts=%d shots=%d", seen, shots))
log:close()
if client.exit then pcall(client.exit) end
