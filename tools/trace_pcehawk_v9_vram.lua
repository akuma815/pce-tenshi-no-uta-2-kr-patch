-- PCEHawk 전용: V9 실행 중 VRAM 에 풀 바이트(한글 텍스트/인덱스/트랩)가
-- 스테이징되는지 자동 탐지. 헤더 없는 원본 카드(cfg_pcehawk_diag)로 실행.
-- 화면 좌상단: 상태. VRAM HIT 시 빨간 표시 + 로그 + VRAM 스냅샷 저장.
-- K 키 = 수동 마킹(스크린샷+VRAM 덤프).

local unpack = unpack or table.unpack
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\v9_probe\pcehawk_vram]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')
local REF = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\v9_probe]]

local log = assert(io.open(OUTDIR .. [[\vram_probe.tsv]], "w"))

-- 도메인 확인
local names = memory.getmemorydomainlist()
local hdr, VRAM, SCD = {}, nil, nil
for i = 0, 200 do
  local n = names[i]
  if n then
    hdr[#hdr + 1] = n
    if string.lower(n) == "vram" or string.find(string.lower(n), "vram") then VRAM = VRAM or n end
    if string.find(n, "Super System Card") then SCD = n end
  end
end
log:write("# domains: " .. table.concat(hdr, " | ") .. "\n")
log:write("# using VRAM=" .. tostring(VRAM) .. " SCD=" .. tostring(SCD) .. "\n")
log:write("frame\tevent\tdetail\n") log:flush()
if not VRAM then
  console.log("VRAM 도메인 없음! domains: " .. table.concat(hdr, " | "))
end

-- 풀 needle 로드 (참조 bin 앞부분 16B — 한글 텍스트/인덱스 식별용)
local function needle(path, off)
  local f = assert(io.open(path, "rb"))
  f:seek("set", off)
  local s = f:read(16)
  f:close()
  return s
end
local NEEDLES = {
  { "pool7A", needle(REF .. [[\pool_7A7B.bin]], 0) },
  { "pool7A+4k", needle(REF .. [[\pool_7A7B.bin]], 0x1000) },
  { "pool7B", needle(REF .. [[\pool_7A7B.bin]], 0x2000) },
  { "pool7E", needle(REF .. [[\pool_7E.bin]], 0) },
  { "idx6D", needle(REF .. [[\pool_6D.bin]], 0) },
  { "trap", string.rep(string.char(0x00, 0xE7), 8) },
}

local vsize = VRAM and memory.getmemorydomainsize(VRAM) or 0
if vsize > 0x20000 then vsize = 0x20000 end
log:write(string.format("# vram size 0x%X\n", vsize)) log:flush()

local function read_domain(dom, off, len)
  local parts = {}
  local pos = off
  local remain = len
  while remain > 0 do
    local n = math.min(remain, 4096)
    local t = memory.readbyterange(pos, n, dom)
    for i = 0, n - 1, 256 do
      local m = math.min(256, n - i)
      local seg = {}
      for j = 1, m do seg[j] = t[i + j - 1] end
      parts[#parts + 1] = string.char(unpack(seg))
    end
    pos = pos + n
    remain = remain - n
  end
  return table.concat(parts)
end

local nhits, lasthit, mark_n, mark_held = 0, "", 0, false
local snap_done = {}
for f = 1, 99999999 do
  emu.frameadvance()
  local keys = input.get()
  if keys["K"] and not mark_held then
    mark_held = true
    mark_n = mark_n + 1
    client.screenshot(string.format("%s\\mark%d_f%d.png", OUTDIR, mark_n, f))
    if VRAM then
      local v = read_domain(VRAM, 0, vsize)
      local mf = assert(io.open(string.format("%s\\mark%d_vram.bin", OUTDIR, mark_n), "wb"))
      mf:write(v) mf:close()
    end
    log:write(string.format("%d\tMARK\t%d\n", f, mark_n)) log:flush()
  elseif not keys["K"] then
    mark_held = false
  end
  if VRAM and f % 60 == 0 then
    local v = read_domain(VRAM, 0, vsize)
    for _, nd in ipairs(NEEDLES) do
      local pos = string.find(v, nd[2], 1, true)
      if pos then
        nhits = nhits + 1
        lasthit = string.format("%s @VRAM 0x%X f%d", nd[1], pos - 1, f)
        log:write(string.format("%d\tVRAMHIT\t%s off 0x%X\n", f, nd[1], pos - 1)) log:flush()
        if not snap_done[nd[1]] then
          snap_done[nd[1]] = true
          local sf = assert(io.open(string.format("%s\\hit_%s_f%d.bin", OUTDIR, nd[1], f), "wb"))
          sf:write(v) sf:close()
          client.screenshot(string.format("%s\\hit_%s_f%d.png", OUTDIR, nd[1], f))
        end
      end
    end
  end
  gui.text(4, 4, string.format("vramprobe f%d hits %d", f, nhits), "white")
  if nhits > 0 then gui.text(4, 20, "VRAM HIT " .. lasthit, "red") end
end
