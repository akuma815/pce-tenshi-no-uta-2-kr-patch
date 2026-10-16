-- V9 전투 깨짐 채증 (TurboNyma, 폴링 전용 — 콜백 불사용)
-- 목적: 전투 깨짐 프레임에서 (1) 풀 뱅크가 POOL/ORIG 어느 상태였는지,
--       (2) VRAM 타일에 풀 바이트(트랩 00E7·한글 텍스트)가 들어갔는지 채증.
-- 사용: EmuHawk --lua=이파일 로 로드 후 그냥 플레이. 깨지면 일시정지만 하면 됨.
-- 출력: translation/b4_debug_2026-08-23/v9_probe/ (프로젝트 내, 세션 무관 고정 경로)

local unpack = unpack or table.unpack

local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\v9_probe]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')

local log = assert(io.open(OUTDIR .. [[\v9_frames.tsv]], "w"))
log:write("frame\tsig7A\tsig7E\tmagic6D\tFLAG\tPRESENT\tstate\n")
log:flush()

local SCD = "Super System Card RAM"   -- banks $68-$7F: off = (bank-$68)*0x2000
local CD  = "TurboCD RAM"             -- banks $80-$87: off = (bank-$80)*0x2000
local OFF_7A, OFF_7E, OFF_6D = 0x24000, 0x2C000, 0x0A000
local FLAG_OFF, PRESENT_OFF = 0x0F9B, 0x88FE   -- CD 도메인 (bank $80 / $84)

-- VRAM 도메인 탐색 (이름에 VRAM 포함)
local vram_domains = {}
local names = memory.getmemorydomainlist()
local hdr = {}
for i = 0, #names do
  local n = names[i]
  if n then
    hdr[#hdr + 1] = n
    if string.find(string.lower(n), "vram") then vram_domains[#vram_domains + 1] = n end
  end
end
log:write("# domains: " .. table.concat(hdr, " | ") .. "\n")
log:write("# vram: " .. table.concat(vram_domains, " | ") .. "\n")
log:flush()

local function sig(dom, off)
  return string.format("%02x%02x%02x%02x",
    memory.read_u8(off, dom), memory.read_u8(off + 1, dom),
    memory.read_u8(off + 2, dom), memory.read_u8(off + 3, dom))
end

local function dump(dom, off, len, path)
  local f = assert(io.open(path, "wb"))
  local pos = off
  local remain = len
  while remain > 0 do
    local n = math.min(remain, 4096)
    local t = memory.readbyterange(pos, n, dom)
    local parts = {}
    for i = 0, n - 1, 256 do
      local m = math.min(256, n - i)
      local seg = {}
      for j = 1, m do seg[j] = t[i + j - 1] end
      parts[#parts + 1] = string.char(unpack(seg))
    end
    f:write(table.concat(parts))
    pos = pos + n
    remain = remain - n
  end
  f:close()
end

local POOL7E, ORG7E = "25663023", "07070707"
local prev = ""
local slot = 0
local mark_n, mark_held = 0, false
for f = 1, 99999999 do
  emu.frameadvance()
  -- K 키 = 깨짐 마킹: 스크린샷 + 뱅크 원샷 덤프 + 로그 표식
  local keys = input.get()
  if keys["K"] and not mark_held then
    mark_held = true
    mark_n = mark_n + 1
    client.screenshot(string.format("%s\\mark%d_f%d.png", OUTDIR, mark_n, f))
    dump(SCD, OFF_7A, 0x4000, string.format("%s\\mark%d_bank7A7B.bin", OUTDIR, mark_n))
    dump(SCD, OFF_7E, 0x2000, string.format("%s\\mark%d_bank7E.bin", OUTDIR, mark_n))
    dump(SCD, OFF_6D, 0x1000, string.format("%s\\mark%d_bank6D.bin", OUTDIR, mark_n))
    log:write(string.format("%d\t# MARK %d\n", f, mark_n))
    log:flush()
  elseif not keys["K"] then
    mark_held = false
  end
  local s7a, s7e = sig(SCD, OFF_7A), sig(SCD, OFF_7E)
  local m6d = sig(SCD, OFF_6D)
  local flag = memory.read_u8(FLAG_OFF, CD)
  local pres = memory.read_u8(PRESENT_OFF, CD)
  local st = "OTHER"
  if s7e == POOL7E then st = "POOL"
  elseif s7e == ORG7E then st = "ORIG482" end
  local line = s7a .. "|" .. s7e .. "|" .. m6d .. "|" .. flag .. "|" .. pres
  if line ~= prev or f % 600 == 0 then
    prev = line
    log:write(string.format("%d\t%s\t%s\t%s\t%02X\t%02X\t%s\n", f, s7a, s7e, m6d, flag, pres, st))
    log:flush()
  end
  if f % 60 == 0 then                      -- 1초마다 롤링 덤프 (8슬롯 순환)
    slot = (slot % 8) + 1
    local tag = string.format("s%d", slot)
    for i, vd in ipairs(vram_domains) do
      local sz = memory.getmemorydomainsize(vd)
      if sz > 0x20000 then sz = 0x20000 end
      dump(vd, 0, sz, string.format("%s\\vram%d_%s.bin", OUTDIR, i, tag))
    end
    dump(SCD, OFF_7A, 0x4000, OUTDIR .. "\\bank7A7B_" .. tag .. ".bin")
    dump(SCD, OFF_7E, 0x2000, OUTDIR .. "\\bank7E_" .. tag .. ".bin")
    dump(SCD, OFF_6D, 0x1000, OUTDIR .. "\\bank6D_" .. tag .. ".bin")
    local mf = assert(io.open(OUTDIR .. "\\last_slot.txt", "w"))
    mf:write(string.format("%s frame %d state %s PRESENT %02X", tag, f, st, pres))
    mf:close()
  end
end
