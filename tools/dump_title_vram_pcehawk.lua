-- 타이틀 화면 조사: 부팅 후 일정 프레임마다 스크린샷 + VRAM(64KB) + VCE 팔레트(512B) 덤프.
-- PCEHawk + 원본 디스크 + 원본 무헤더 카드 (cfg_b13.ini). 입력 없음 → 타이틀에 머문다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\title_probe]]
local log = assert(io.open(OUTDIR .. "/dump.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function dump(tag)
  local f = assert(io.open(string.format("%s/vram_%s.bin", OUTDIR, tag), "wb"))
  local t = {}
  for a = 0, 0xFFFF do t[#t+1] = string.char(memory.read_u8(a, "VRAM1")) end
  f:write(table.concat(t)); f:close()
  local p = assert(io.open(string.format("%s/pal_%s.bin", OUTDIR, tag), "wb"))
  local u = {}
  for a = 0, 0x3FF do
    local ok, v = pcall(memory.read_u8, a, "VCEPalette")
    u[#u+1] = string.char(ok and v or 0)
  end
  p:write(table.concat(u)); p:close()
  pcall(client.screenshot, string.format("%s/shot_%s.png", OUTDIR, tag))
  say("dump " .. tag .. " frame=" .. emu.framecount())
end
local marks = { [2700]=true }
for f = 1, 2750 do
  emu.frameadvance()
  if marks[f] then dump(string.format("f%04d", f)) end
end
say("done")
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
