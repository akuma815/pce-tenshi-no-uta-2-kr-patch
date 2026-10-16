-- PCEHawk: 전투 창 차셋(VRAM tile 0x650) 변화 프레임 감시 + 뱅크/PRESENT 타임라인.
-- V9 와 원본 양쪽에서 같은 코스를 돌려 "차셋이 언제/무엇으로 바뀌는지"를 비교한다.
-- K 키 = 스크린샷+VRAM 전체 덤프 마킹.

local unpack = unpack or table.unpack
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\v9_probe\charset_watch]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')

-- 게임 이름으로 로그 파일 구분
local gi = gameinfo.getromname and gameinfo.getromname() or "unknown"
local tag = string.find(gi, "V9") and "v9" or (string.find(gi, "V13") and "v13" or "orig")
local log = assert(io.open(string.format("%s\\charset_%s.tsv", OUTDIR, tag), "w"))
log:write("# rom: " .. gi .. "\n")
log:write("frame\tevent\tdetail\n") log:flush()

local VRAM, SCD, CD = "VRAM1", "Super System Card RAM", "TurboCD RAM"
local T650, T65D = 0x650 * 32, 0x65D * 32   -- VRAM 바이트 오프셋
local OFF_7A, OFF_7E, OFF_6D = 0x24000, 0x2C000, 0x0A000
local FLAG_OFF, PRESENT_OFF = 0x0F9B, 0x88FE

local function rd(dom, off, len)
  local t = memory.readbyterange(off, len, dom)
  local seg = {}
  for j = 1, len do seg[j] = t[j - 1] end
  return string.char(unpack(seg))
end

local function hex(s)
  return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

local function dumpfile(path, dom, off, len)
  local f = assert(io.open(path, "wb"))
  local pos, remain = off, len
  while remain > 0 do
    local n = math.min(remain, 4096)
    f:write(rd(dom, pos, n))
    pos = pos + n
    remain = remain - n
  end
  f:close()
end

local prev650, prev65d, prevsig = "", "", ""
local mark_n, mark_held = 0, false
for f = 1, 99999999 do
  emu.frameadvance()
  local keys = input.get()
  if keys["K"] and not mark_held then
    mark_held = true
    mark_n = mark_n + 1
    client.screenshot(string.format("%s\\%s_mark%d_f%d.png", OUTDIR, tag, mark_n, f))
    dumpfile(string.format("%s\\%s_mark%d_vram.bin", OUTDIR, tag, mark_n), VRAM, 0, 0x10000)
    log:write(string.format("%d\tMARK\t%d\n", f, mark_n)) log:flush()
  elseif not keys["K"] then
    mark_held = false
  end

  local c650 = rd(VRAM, T650, 32)
  local c65d = rd(VRAM, T65D, 32)
  if c650 ~= prev650 then
    prev650 = c650
    log:write(string.format("%d\tT650\t%s\n", f, hex(c650))) log:flush()
  end
  if c65d ~= prev65d then
    prev65d = c65d
    log:write(string.format("%d\tT65D\t%s\n", f, hex(c65d))) log:flush()
  end

  local sig = hex(rd(SCD, OFF_7A, 4)) .. "|" .. hex(rd(SCD, OFF_7E, 4)) .. "|" ..
      hex(rd(SCD, OFF_6D, 4)) .. "|" ..
      string.format("%02X", memory.read_u8(PRESENT_OFF, CD))
  if sig ~= prevsig then
    prevsig = sig
    log:write(string.format("%d\tBANKS\t%s\n", f, sig)) log:flush()
  end

  gui.text(4, 4, string.format("charset-watch[%s] f%d", tag, f), "white")
end
