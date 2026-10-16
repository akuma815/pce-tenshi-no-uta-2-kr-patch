-- Z11 프로브 v5 — 런타임 창/글자 위치 검출의 기반 조사
--   (1) PCEHawk 가 노출하는 레지스터 전수 (VDC BAT base·스크롤 확인)
--   (2) 메모리 도메인 크기
--   (3) 텍스트 버스트 전/후 VRAM diff → 글자가 어느 BAT 셀에 들어가는가
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local BUDGET = 6000
local QUIET  = 10

local log = assert(io.open(OUTDIR .. "/v5.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

-- ---------- 1. 레지스터 전수 ----------
local ok, regs = pcall(emu.getregisters)
if ok and regs then
  local keys = {}
  for k in pairs(regs) do keys[#keys+1] = tostring(k) end
  table.sort(keys)
  local parts = {}
  for _, k in ipairs(keys) do parts[#parts+1] = string.format("%s=%s", k, tostring(regs[k])) end
  say("REGS: " .. table.concat(parts, " "))
end

-- ---------- 2. 도메인 크기 ----------
for _, d in ipairs({"VRAM1", "VCEPalette", "Main Memory", "System Bus"}) do
  local ok2, sz = pcall(memory.getmemorydomainsize, d)
  say(string.format("DOMAIN %-14s size=%s", d, ok2 and tostring(sz) or "N/A"))
end

-- ---------- 3. VRAM diff ----------
local VR = "VRAM1"
local vsize = select(2, pcall(memory.getmemorydomainsize, VR)) or 65536
local SCAN = math.min(vsize, 65536)

local function snap()
  local ok3, a = pcall(memory.read_bytes_as_array, 0, SCAN, VR)
  return ok3 and a or nil
end

local function diff(a, b)
  if not a or not b then return {} end
  local runs, cur = {}, nil
  for i = 1, SCAN do
    if a[i] ~= b[i] then
      if cur and i - cur.e <= 8 then cur.e = i; cur.n = cur.n + 1
      else cur = { s = i, e = i, n = 1 }; runs[#runs+1] = cur end
    end
  end
  return runs
end

local nhit, last_hit, before, bursts = 0, -1000, nil, 0
local chars = {}

event.on_bus_exec(function()
  if nhit == 0 or (emu.framecount() - last_hit) >= QUIET then
    before = snap()                       -- 버스트 시작 직전 스냅
    chars = {}
  end
  nhit = nhit + 1
  last_hit = emu.framecount()
  chars[#chars+1] = string.format("%02X%02X",
    memory.read_u8(0x2000+0xF9,"System Bus"), memory.read_u8(0x2000+0xF8,"System Bus"))
end, 0x967E, "v5 hook", "System Bus")

pcall(client.speedmode, 300)
say("v5 start  scan=" .. SCAN)
for f = 1, BUDGET do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  emu.frameadvance()
  if nhit > 0 and (f - (last_hit - 0)) >= QUIET and before and #chars > 0 then
    bursts = bursts + 1
    local after = snap()
    local runs = diff(before, after)
    local o = emu.getregisters and select(2, pcall(emu.getregisters)) or {}
    say(string.format("--- burst %d  f%d  %d글자  변경런 %d ---", bursts, f, #chars, #runs))
    local shown = 0
    for _, r in ipairs(runs) do
      if r.n >= 4 and shown < 12 then
        say(string.format("    VRAM $%05X..$%05X  (%d B)", r.s-1, r.e-1, r.n))
        shown = shown + 1
      end
    end
    pcall(client.screenshot, string.format("%s/v5_b%02d_f%05d.png", OUTDIR, bursts, f))
    before = nil; chars = {}
    if bursts >= 6 then break end
  end
end
say("done bursts=" .. bursts .. " hits=" .. nhit)
log:close()
if client.exit then pcall(client.exit) end
