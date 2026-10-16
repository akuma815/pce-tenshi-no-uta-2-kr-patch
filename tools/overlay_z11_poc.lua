-- Z11.1 오버레이 PoC — 런타임 BAT 검출 + 창 배경색 팔레트 산출 + 세그먼트별 한글
-- 구조: 12px 글자는 8px BAT 행 2개에 걸친다 -> 인접 행을 묶으면 텍스트 줄,
--       줄 안의 칼럼 런이 세그먼트. 세그먼트 순서 = 번역 '|' 순서.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local CSV    = OUTDIR .. "/overlay_poc.csv"
local BAT_STRIDE, BAT_COLS, BAT_SCAN = 0x80, 64, 0x1000
local QUIET, VR = 8, "VRAM1"

local log = assert(io.open(OUTDIR .. "/overlay_poc.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local KO = {}
do
  local n, f = 0, io.open(CSV, "r")
  if f then
    f:read("*l")
    for line in f:lines() do
      local k, _, v = line:match("^([^\t]*)\t([^\t]*)\t(.*)$")
      if k and v and #k > 0 then
        local segs = {}
        for s in (v .. "|"):gmatch("([^|]*)|") do segs[#segs+1] = s end
        KO[k] = segs; n = n + 1
      end
    end
    f:close()
  end
  say("번역표 " .. n .. "건 적재")
end

local function vb(a) return memory.read_u8(a, VR) end
local function bat(r, c) local a = r*BAT_STRIDE + c*2; return vb(a) + vb(a+1)*256 end
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
  local b = t*32
  local m = 2 ^ (7-x)
  local function bit(p) return math.floor(p/m) % 2 end
  return bit(vb(b+y*2)) + bit(vb(b+y*2+1))*2 + bit(vb(b+16+y*2))*4 + bit(vb(b+16+y*2+1))*8
end

local before, chars, nhit, last_hit, show = nil, {}, 0, -1000, nil
local function snap() local ok, a = pcall(memory.read_bytes_as_array, 0, BAT_SCAN, VR); return ok and a or nil end

event.on_bus_exec(function()
  local f = emu.framecount()
  if nhit == 0 or (f - last_hit) >= QUIET then before = snap(); chars = {} end
  nhit = nhit + 1; last_hit = f
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "Z11 overlay", "System Bus")

-- 변경 셀 -> 행별 칼럼 런 -> 인접 행 병합 -> 세그먼트
local function segments(a, b)
  if not a or not b then return {} end
  local perrow = {}
  for i = 1, BAT_SCAN, 2 do
    if a[i] ~= b[i] or a[i+1] ~= b[i+1] then
      local off = i-1
      local r, c = math.floor(off/BAT_STRIDE), math.floor((off % BAT_STRIDE)/2)
      perrow[r] = perrow[r] or {}; perrow[r][#perrow[r]+1] = c
    end
  end
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
  table.sort(runs, function(x, y) if x.r ~= y.r then return x.r < y.r end return x.c0 < y.c0 end)
  -- 인접 행 + 칼럼 겹침 -> 병합 (12px 글자가 두 행에 걸침)
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
  table.sort(out, function(x, y) if x.r ~= y.r then return x.r < y.r end return x.c0 < y.c0 end)
  return out
end

local function window_color(segs)
  for _, q in ipairs(segs) do
    local c = (q.c0 > 0) and (q.c0 - 1) or (q.c1 + 1)
    if c >= 0 and c < BAT_COLS then
      local e = bat(q.r, c)
      local t, p = e % 4096, math.floor(e/4096)
      local idx = tile_pixel(t, 4, 4)
      local rgb, R, G, B = pal_rgb(p, idx)
      if rgb then return rgb, string.format("pal=%d idx=%d GRB=%d,%d,%d", p, idx, G, R, B) end
    end
  end
  return 0xFF000000, "fallback"
end

local dbg_once = {}
local function try(label, fn, ...)
  local ok, err = pcall(fn, ...)
  if dbg_once[label] == nil then
    dbg_once[label] = true
    say("  GUI " .. label .. " -> " .. (ok and "OK" or ("ERR: " .. tostring(err))))
  end
  return ok
end

local function draw()
  try("use_surface", gui.use_surface, "emucore")   -- 조기 반환보다 먼저
  if not show then return end
  local PAD = 6
  -- 1패스: 원문을 전부 덮는다 (뒤 세그먼트가 앞 세그먼트 글자를 지우지 않도록 분리)
  for _, q in ipairs(show.segs) do
    local x, y = q.c0*8 - PAD, q.r*8 - PAD
    local w, h = (q.c1-q.c0+1)*8 + PAD*2, q.h*8 + PAD*2
    if x < 0 then w = w + x; x = 0 end
    if y < 0 then h = h + y; y = 0 end
    try("drawRectangle", gui.drawRectangle, x, y, w, h, show.color, show.color)
  end
  -- 2패스: 한글을 원래 글자 자리에 그린다
  for i, q in ipairs(show.segs) do
    local t = show.text[i]
    if t and #t > 0 then
      try("drawText", gui.drawText, q.c0*8, q.r*8 - 1, t,
          0xFFFFFFFF, show.color, 12, "Malgun Gothic")
    end
  end
end

pcall(client.speedmode, 300)
local surf_ok = pcall(gui.use_surface, "emucore")   -- v3 와 동일하게 시작 시점에 한 번
say("gui.use_surface('emucore') -> " .. tostring(surf_ok))
local osd_ok = pcall(client.setscreenshotosd, true) -- ★ 스크린샷에 Lua 레이어 포함
say("client.setscreenshotosd(true) -> " .. tostring(osd_ok))
say("overlay PoC 가동")
local shots = 0
for f = 1, 14000 do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  -- ★ last_hit 은 emu.framecount() 기준이다. 루프 변수 f 와 섞으면
  --   상태 로드 후 프레임 번호가 어긋나 버스트 종료가 영영 성립하지 않는다.
  if nhit > 0 and before and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    local key = table.concat(chars, "")
    local ko = KO[key]
    if ko then
      local segs = segments(before, snap())
      if #segs > 0 then
        local col, dbg = window_color(segs)
        show = { segs = segs, color = col, text = ko }
        say(string.format("HIT f%d  %d글자  세그먼트=%d개 (번역 %d개)  색=%08X %s",
            f, #chars, #segs, #ko, col, dbg))
        for i, q in ipairs(segs) do
          say(string.format("    seg%d 행%d..%d 칼럼%d..%d  px=(%d,%d) %dx%d  ko=%s",
              i, q.r, q.r+q.h-1, q.c0, q.c1, q.c0*8, q.r*8,
              (q.c1-q.c0+1)*8, q.h*8, tostring(ko[i])))
        end
        for i = 1, 10 do draw(); emu.frameadvance() end
        shots = shots + 1
        pcall(client.screenshot, string.format("%s/poc_%02d_f%05d.png", OUTDIR, shots, f))
        if shots >= 4 then break end
      end
    end
    before = nil; chars = {}
  end
  draw()
  emu.frameadvance()
end
say("done shots=" .. shots)
log:close()
if client.exit then pcall(client.exit) end
