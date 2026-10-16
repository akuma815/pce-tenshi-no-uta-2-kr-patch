-- Z11 통합 오버레이 — 창 앵커 자기보정 + 원점 역산 + 창 내부 필터
--
-- 확정 근거 (전부 실측):
--   §4e 지상검증: BAT 64x32 / base $0000 / GRB / 셀->화면 = (col*8-OX) mod 512, (row*8-OY) mod 256
--   §4e 앵커검증: 원점 = BAT채움블록시작 - (창화면시작 + border_off)
--                border_off = ((창화면폭 - 채움칼럼수*8)/2, (창화면높이 - 채움행수*8)/2)
--                -> 하드코딩 상수 0개로 정답 (352,82) 재현 확인
--   검출: 버스트 전/후 BAT diff. 노이즈는 창 밖이므로 창 rect 로 걸러낸다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local CSV    = OUTDIR .. "/overlay_subtitles.csv"   -- build_overlay_subtitles.py 산출
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
-- ★ QUIET 는 **수확기(harvest_z11_windows.lua)와 반드시 같아야 한다**.
--   버스트 경계가 달라지면 원문 키가 달라져 번역표가 통째로 안 맞는다(실측 MISS).
local VR, QUIET = "VRAM1", 12
local CHARW = 12                      -- 글자 폭(px) — 자기검증 기준 (§4f 실측)
local BC, BR = 64, 32                 -- BAT 칼럼/행
local PW, PH = BC*8, BR*8             -- 512, 256

-- 창 클래스 정적 표 — translation/z11_probe/classes.lua (build_overlay_classes.py 산출).
-- ★ 여기에 표를 복사해 두지 않는다. 수확을 넓힐 때마다 표가 바뀌는데,
--   손으로 옮겨 적으면 실측과 어긋나고 어긋난 클래스는 원점을 통째로 틀린다.
--   재생성: python -X utf8 tools/build_overlay_classes.py
local CLASSES = assert(dofile(OUTDIR .. "/classes.lua"), "classes.lua 적재 실패")

-- 두 가지 모드를 한 파일로 돌린다 (표를 복사해 두지 않는 것과 같은 이유 — 사본은 어긋난다).
--   기본       = 회귀 검증. 세이브스테이트 로드 -> 2버스트 캡처 -> 종료.
--   PLAY 모드  = 사람이 켜 놓고 플레이. 상태 로드/자동입력/스크린샷/종료 전부 없음.
-- PLAY 진입점 = tools/overlay_z11_play.lua (Z11_PLAY 를 세우고 이 파일을 dofile).
local PLAY = (Z11_PLAY == true)
local log = assert(io.open(OUTDIR .. (PLAY and "/z11_play.log" or "/z11_final.log"), "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local KO = {}
do
  local n, f = 0, io.open(CSV, "r")
  if f then
    f:read("*l")
    for line in f:lines() do
      -- 생성기 출력은 5열(sjis_hex, source, text_ko, miss, segs)이므로
      -- 세 번째 열만 취한다 (뒤 열이 번역문에 붙지 않도록).
      local k, _, v = line:match("^([^\t]*)\t([^\t]*)\t([^\t]*)")
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
local function bat(r, c) local a = (r*BC + c)*2; return vb(a) + vb(a+1)*256 end
local function pal_rgb(p, i)
  local e = (p*16 + i)*2
  local ok, lo = pcall(memory.read_u8, e, "VCEPalette")
  local ok2, hi = pcall(memory.read_u8, e+1, "VCEPalette")
  if not (ok and ok2) then return nil end
  local v = lo + hi*256
  local B, R, G = v % 8, math.floor(v/8) % 8, math.floor(v/64) % 8
  local function s(x) return math.floor(x*255/7) end
  return 0xFF000000 + s(R)*0x10000 + s(G)*0x100 + s(B)
end
local function tile_pixel(t, x, y)
  local b, m = t*32, 2 ^ (7-x)
  local function bit(p) return math.floor(p/m) % 2 end
  return bit(vb(b+y*2)) + bit(vb(b+y*2+1))*2 + bit(vb(b+16+y*2))*4 + bit(vb(b+16+y*2+1))*8
end

-- 랩을 고려해 가장 좁게 감싸는 (시작, 길이)
local function wrap_span(set, size)
  local vals = {}
  for v in pairs(set) do vals[#vals+1] = v end
  if #vals == 0 then return nil end
  table.sort(vals)
  local bs, bl = vals[1], 1e9
  for i = 1, #vals do
    local st, len = vals[i], 0
    for j = 1, #vals do
      local d = (vals[j] - st) % size
      if d + 1 > len then len = d + 1 end
    end
    if len < bl then bl, bs = len, st end
  end
  return bs, bl
end

-- BAT 에서 창 채움 블록을 찾아 원점을 역산.
-- ★ 후보를 하나로 좁히지 않고 **점수 내림차순 목록**으로 돌려준다.
--   같은 크기·다른 위치 클래스가 실제로 있다(c006D00_316x60 이 sy=144 와 sy=16,
--   c006D00_348x60 이 sy=160 과 161). 크기만 보면 잘못 고르고 원점이 통째로
--   틀어진다. 최종 선택은 호출부가 "창 안에 텍스트 셀이 가장 많이 잡히는가"로
--   자기검증해서 한다 — 틀린 클래스는 셀이 거의 안 잡힌다.
local MAXCAND = 12
local function find_candidates()
  local cnt, cells = {}, {}
  for r = 0, BR-1 do
    for c = 0, BC-1 do
      local e = bat(r, c)
      local k = e                              -- (타일,팔레트) 통째로 키
      cnt[k] = (cnt[k] or 0) + 1
      cells[k] = cells[k] or { cs = {}, rs = {} }
      cells[k].cs[c] = true; cells[k].rs[r] = true
    end
  end
  local out = {}
  for k, n in pairs(cnt) do
    if n >= 30 then
      local cs, cl = wrap_span(cells[k].cs, BC)
      local rs, rl = wrap_span(cells[k].rs, BR)
      if cs and rs then
        for _, cl2 in ipairs(CLASSES) do
          -- 블록은 창 안쪽이므로 화면크기보다 작고, 차이는 테두리 폭(양쪽 합)이다
          local dw, dh = cl2.sw - cl*8, cl2.sh - rl*8
          if dw >= 0 and dw <= 20 and dh >= 0 and dh <= 20 then
            local fill = n / (cl * rl)
            local offx = math.floor((cl2.sw - cl*8) / 2)
            local offy = math.floor((cl2.sh - rl*8) / 2)
            out[#out+1] = {
              key = k, n = n, cs = cs, rs = rs, cl = cl, rl = rl,
              cls = cl2, fill = fill, score = fill * (cl * rl) - (dw + dh),
              offx = offx, offy = offy,
              ox = (cs*8 - (cl2.sx + offx)) % PW,
              oy = (rs*8 - (cl2.sy + offy)) % PH,
            }
          end
        end
      end
    end
  end
  table.sort(out, function(a, b) return a.score > b.score end)
  while #out > MAXCAND do table.remove(out) end
  return out
end

local chars, nhit, last_hit, before, show = {}, 0, -10000, nil, nil
local function snap()
  local ok, a = pcall(memory.read_bytes_as_array, 0, BC*BR*2, VR)
  return ok and a or nil
end

if not PLAY then
  for i = 1, 20 do emu.frameadvance() end
  say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
  for i = 1, 5 do emu.frameadvance() end
end

event.on_bus_exec(function()
  local fc = emu.framecount()
  if nhit == 0 or (fc - last_hit) >= QUIET then
    before = snap(); chars = {}
    show = nil          -- 새 버스트가 시작되면 앞 창의 오버레이는 그 즉시 낡은 것이다
  end
  nhit = nhit + 1; last_hit = fc
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "chr", "System Bus")

-- 변경 셀 -> 화면좌표 변환 -> 창 안만 남김 -> 세그먼트
local function detect(a, b, ox, oy, cls)
  local out = {}
  if not a or not b then return out end
  for i = 1, BC*BR*2, 2 do
    if a[i] ~= b[i] or a[i+1] ~= b[i+1] then
      local w = math.floor((i-1)/2)
      local r, c = math.floor(w/BC), w % BC
      local x, y = (c*8 - ox) % PW, (r*8 - oy) % PH
      if x >= cls.sx and x < cls.sx + cls.sw and y >= cls.sy and y < cls.sy + cls.sh then
        out[#out+1] = { x = x, y = y }
      end
    end
  end
  return out
end

local function to_segments(cells)
  local byrow = {}
  for _, p in ipairs(cells) do
    byrow[p.y] = byrow[p.y] or {}
    table.insert(byrow[p.y], p.x)
  end
  local runs = {}
  for y, xs in pairs(byrow) do
    table.sort(xs)
    local s, p = xs[1], xs[1]
    for i = 2, #xs do
      if xs[i] - p > 16 then runs[#runs+1] = {y=y, x0=s, x1=p+7, h=8}; s = xs[i] end
      p = xs[i]
    end
    runs[#runs+1] = {y=y, x0=s, x1=p+7, h=8}
  end
  table.sort(runs, function(a,b) if a.y~=b.y then return a.y<b.y end return a.x0<b.x0 end)
  local out, used = {}, {}
  for i, q in ipairs(runs) do
    if not used[i] then
      local seg = {y=q.y, x0=q.x0, x1=q.x1, h=8}
      for j = i+1, #runs do
        local w = runs[j]
        if not used[j] and seg.h < 16 and w.y == seg.y + seg.h
           and w.x0 <= seg.x1 + 8 and w.x1 >= seg.x0 - 8 then
          seg.x0 = math.min(seg.x0, w.x0); seg.x1 = math.max(seg.x1, w.x1)
          seg.h = seg.h + 8; used[j] = true
        end
      end
      out[#out+1] = seg
    end
  end
  table.sort(out, function(a,b) if a.y~=b.y then return a.y<b.y end return a.x0<b.x0 end)
  return out
end

local function draw()
  pcall(gui.use_surface, "emucore")
  if not show then return end
  -- 창이 사라졌으면(메뉴 닫힘·씬 전환) 오버레이도 즉시 걷는다.
  local ok, cur = pcall(bat, show.pr, show.pc)
  if not ok or cur ~= show.key then show = nil; return end
  local PAD = 6
  for i, q in ipairs(show.segs) do
    local t = show.text[i]
    local w = q.x1 - q.x0 + 1
    -- ★ 번역이 없는 세그먼트는 덮지 않는다.
    --   덮기만 하면 원문 자리에 빈 구멍이 남아 원문을 두는 것보다 나쁘다.
    --   (입력 대기 커서 같은 소형 조각도 같은 규칙으로 보존된다)
    if t and #t > 0 then
      pcall(gui.drawRectangle, q.x0-PAD, q.y-PAD, w+PAD*2, q.h+PAD*2,
            show.color, show.color)
    end
  end
  for i, q in ipairs(show.segs) do
    local t = show.text[i]
    if t and #t > 0 then
      pcall(gui.drawText, q.x0, q.y - 1, t, 0xFFFFFFFF, show.color, 12, "Malgun Gothic")
    end
  end
end

pcall(client.setscreenshotosd, true)
pcall(gui.use_surface, "emucore")
pcall(client.speedmode, 100)
say("Z11 통합 오버레이 가동")

local shots, seen, miss = 0, 0, 0
local f = 0
while PLAY or f < 2400 do
  f = f + 1
  -- 자동 입력은 회귀 모드 전용. PLAY 에서는 사람이 조작한다.
  if not PLAY then pcall(joypad.set, { B1 = (f % 60 < 30) }, 1) end
  if nhit > 0 and #chars > 0 and (emu.framecount() - last_hit) >= QUIET then
    seen = seen + 1
    local key = table.concat(chars, "")
    local ko  = KO[key]
    -- 매처 자기검증: 크기만으로는 클래스가 하나로 안 좁혀지므로 후보마다 실제로
    -- 검출을 돌려 본다. 채택 기준은 아래 참조.
    local after = snap()
    local cands = find_candidates()
    -- ★ 자기검증 기준 = **잡은 글자 폭**. "창 안 셀이 가장 많은 후보"는 틀린 기준이었다
    --   — 큰 rect 일수록 배경 잡음까지 주워 담아 항상 이긴다(실측: 316x188 이 316x60 을
    --   밀어내고 원점이 버스트마다 튐).
    --   물리적 상한이 있다: **그리지도 않은 글자를 잡을 수는 없다.**
    --   글자 수 x 12px 를 넘게 잡은 후보는 배경을 창으로 오인한 것이므로 버린다.
    --   여유: 런의 오른쪽 끝은 8px 셀 경계로 올림되므로 세그먼트마다 최대 8px 가
    --   더 잡힌다. 그래서 여유를 세그먼트 수에 비례시킨다(고정 상수로 두면 줄이 많은
    --   창에서 정답이 탈락한다 — 3세그 408/384 가 고정 여유 24px 에 딱 걸렸다).
    local blk, cells, segs, bestw = nil, nil, nil, -1
    for _, cd in ipairs(cands) do
      local cc = detect(before, after, cd.ox, cd.oy, cd.cls)
      local sg = to_segments(cc)
      local w = 0
      for _, q in ipairs(sg) do w = w + (q.x1 - q.x0 + 1) end
      if w <= #chars * CHARW + 8 * #sg + 8 and w > bestw then
        blk, cells, segs, bestw = cd, cc, sg, w
      end
    end
    -- 통과한 후보가 없으면 **그리지 않는다**. 잘못된 위치에 그리는 것보다
    -- 원문을 두는 편이 낫다(§4g 안전장치와 같은 원칙).
    if blk and bestw < CHARW then blk = nil end
    if blk then
      local ox, oy, offx, offy = blk.ox, blk.oy, blk.offx, blk.offy
      say(string.format("BURST %d %d글자  원점(%d,%d) [%s 블록 col%d row%d %dx%d, off(%d,%d)]  후보%d 창내셀%d 세그%d 폭%d/%d  match=%s",
          seen, #chars, ox, oy, blk.cls.name, blk.cs, blk.rs, blk.cl, blk.rl,
          offx, offy, #cands, #cells, #segs, bestw, #chars * CHARW,
          ko and "YES" or "no"))
      for i = 1, math.min(#segs, 8) do
        local q = segs[i]
        say(string.format("    seg%d 화면(%d,%d) %dx%d  ko=%s", i, q.x0, q.y,
            q.x1-q.x0+1, q.h, (ko and ko[i]) or ""))
      end
      -- ★ Z11.4 판정 근거: 번역표에 없는 버스트를 원문 키째로 남긴다.
      --   이 줄이 0 이어야 "잔존 일문 0" 이라고 말할 수 있다.
      if not ko then
        miss = miss + 1
        say(string.format("  MISS key=%s", key))
      end
      if ko and #segs > 0 then
        -- 창색 = 채움 블록의 타일/팔레트에서 산출
        local e = blk.key
        local col = pal_rgb(math.floor(e/4096), tile_pixel(e % 4096, 4, 4)) or 0xFF000000
        -- ★ 창이 닫히거나 화면이 바뀌면 스스로 사라져야 한다.
        --   채움 블록 중심 셀이 아직 같은 타일인지 매 프레임 확인한다(§4k 결함 2).
        show = { segs = segs, color = col, text = ko, key = blk.key,
                 pr = (blk.rs + math.floor(blk.rl/2)) % BR,
                 pc = (blk.cs + math.floor(blk.cl/2)) % BC }
        if not PLAY then
          say(string.format("  HIT 색=%08X", col))
          for i = 1, 12 do draw(); emu.frameadvance() end
          shots = shots + 1
          pcall(client.screenshot, string.format("%s/z11_final_%02d.png", OUTDIR, shots))
          if shots >= 2 then break end
        end
      end
    else
      -- 후보가 아예 없거나(창 블록 미검출) 전부 과잉 포획이라 탈락한 경우.
      say(string.format("BURST %d %d글자  창 확정 실패 (후보%d) — 그리지 않음",
          seen, #chars, #cands))
      show = nil
    end
    before = nil; chars = {}
  end
  draw()
  emu.frameadvance()
end
say(string.format("done bursts=%d shots=%d miss=%d", seen, shots, miss))
log:close()
if not PLAY and client.exit then pcall(client.exit) end
