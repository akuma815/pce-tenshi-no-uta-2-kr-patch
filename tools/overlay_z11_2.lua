-- Z11.2 — 초상화 대사를 원본보다 긴 한글로 출력 (길이 캡 소멸 실증)
-- 검증된 조각만 조립: probe_input_test.lua(입력) + overlay_z11_poc.lua(검출·렌더)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local CSV    = OUTDIR .. "/overlay_poc.csv"
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local BAT_STRIDE, BAT_COLS, BAT_SCAN = 0x80, 64, 0x1000
local QUIET, VR = 8, "VRAM1"

local log = assert(io.open(OUTDIR .. "/z11_2.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

-- ---------- 상태 (모든 지역변수를 훅보다 먼저 선언) ----------
local before, chars, nhit, last_hit, show = nil, {}, 0, -10000, nil

-- ---------- 번역표 ----------
local KO = {}
do
  local n, f = 0, io.open(CSV, "r")
  if f then
    f:read("*l")
    for line in f:lines() do
      local k, _, v = line:match("^([^\t]*)\t([^\t]*)\t(.*)$")
      if k and v and #k > 0 then
        local segs = {}
        for x in (v .. "|"):gmatch("([^|]*)|") do segs[#segs+1] = x end
        KO[k] = segs; n = n + 1
      end
    end
    f:close()
  end
  say("번역표 " .. n .. "건 적재")
end

-- ---------- VRAM/팔레트 ----------
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
  local b, m = t*32, 2 ^ (7-x)
  local function bit(p) return math.floor(p/m) % 2 end
  return bit(vb(b+y*2)) + bit(vb(b+y*2+1))*2 + bit(vb(b+16+y*2))*4 + bit(vb(b+16+y*2+1))*8
end
local function snap()
  local ok, a = pcall(memory.read_bytes_as_array, 0, BAT_SCAN, VR)
  return ok and a or nil
end

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
  table.sort(runs, function(x,y) if x.r ~= y.r then return x.r < y.r end return x.c0 < y.c0 end)
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
  table.sort(out, function(x,y) if x.r ~= y.r then return x.r < y.r end return x.c0 < y.c0 end)
  return out
end

local function window_color(segs)
  for _, q in ipairs(segs) do
    local c = (q.c0 > 0) and (q.c0 - 1) or (q.c1 + 1)
    if c >= 0 and c < BAT_COLS then
      local e = bat(q.r, c)
      local t, p = e % 4096, math.floor(e/4096)
      local rgb, R, G, B = pal_rgb(p, tile_pixel(t, 4, 4))
      if rgb then return rgb, string.format("pal=%d GRB=%d,%d,%d", p, G, R, B) end
    end
  end
  return 0xFF000000, "fallback"
end

local function draw()
  pcall(gui.use_surface, "emucore")
  if not show then return end
  local PAD = 6
  for _, q in ipairs(show.segs) do                    -- 1패스: 전부 덮기
    local x, y = q.c0*8 - PAD, q.r*8 - PAD
    local w, h = (q.c1-q.c0+1)*8 + PAD*2, q.h*8 + PAD*2
    if x < 0 then w = w + x; x = 0 end
    if y < 0 then h = h + y; y = 0 end
    pcall(gui.drawRectangle, x, y, w, h, show.color, show.color)
  end
  for i, q in ipairs(show.segs) do                    -- 2패스: 한글
    local t = show.text[i]
    if t and #t > 0 then
      pcall(gui.drawText, q.c0*8, q.r*8 - 1, t, 0xFFFFFFFF, show.color, 12, "Malgun Gothic")
    end
  end
end

-- ---------- 상태 로드 -> 훅 등록 (입력 테스트와 동일 순서) ----------
for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

event.on_bus_exec(function()
  local fc = emu.framecount()
  if nhit == 0 or (fc - last_hit) >= QUIET then before = snap(); chars = {} end
  nhit = nhit + 1; last_hit = fc
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9, "System Bus"), memory.read_u8(0x2000+0xF8, "System Bus"))
end, 0x967E, "z11_2", "System Bus")
say("훅 등록 완료")

pcall(client.setscreenshotosd, true)
pcall(gui.use_surface, "emucore")
pcall(client.speedmode, 100)

local shots, seen = 0, 0
for f = 1, 2400 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)        -- 입력 테스트에서 최다 히트한 패턴
  if nhit > 0 and before and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    seen = seen + 1
    local key = table.concat(chars, "")
    local ko  = KO[key]
    local segs = segments(before, snap())
    say(string.format("BURST %d  %d글자 세그%d  match=%s", seen, #chars, #segs, ko and "YES" or "no"))
    if not ko then say("      key=" .. key:sub(1, 80)) end
    if ko and #segs > 0 then
      local col, dbg = window_color(segs)
      show = { segs = segs, color = col, text = ko }
      say(string.format("  HIT 세그먼트=%d 번역=%d 색=%08X %s", #segs, #ko, col, dbg))
      for i, q in ipairs(segs) do
        say(string.format("    seg%d 행%d..%d 칼럼%d..%d px=(%d,%d) ko=%s",
            i, q.r, q.r+q.h-1, q.c0, q.c1, q.c0*8, q.r*8, tostring(ko[i])))
      end
      for i = 1, 12 do draw(); emu.frameadvance() end
      shots = shots + 1
      pcall(client.screenshot, string.format("%s/z11_2_%02d.png", OUTDIR, shots))
      if shots >= 3 then break end
    end
    before = nil; chars = {}
  end
  draw()
  emu.frameadvance()
end
say(string.format("done bursts=%d shots=%d nhit=%d", seen, shots, nhit))
log:close()
if client.exit then pcall(client.exit) end
