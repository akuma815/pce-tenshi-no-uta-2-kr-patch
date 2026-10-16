-- b18 조사 실험: diag_battle1.State(b10 RAM) 의 전투 템플릿 '{%s}는{%d}피해!' 를
--   '{%s}' 1F 00 '{%d}피해!' 로 포크한 뒤 공격을 일으켜 훅 상태를 기록한다.
-- 로그: translation/b18_runtime/josa_poke.log
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b18_runtime]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_battle1.State]]
local CD, BUS = "TurboCD RAM", "System Bus (21 bit)"
local log = assert(io.open(OUTDIR .. "/josa_poke.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X LASTHI=%02X LASTLO=%02X EXPECT=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88F2), rd(0x88F3), rd(0x88F5))
end
for i = 1, 40 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
say("t0 " .. st())
-- 씬 뱅크 $68-$7F (phys 0xD0000-0xFFFFF) 에서 템플릿 검색: 25 73 88 A6 25 64 (= {%s}는{%d})
local pat = { 0x25, 0x73, 0x88, 0xA6 }   -- 엔진 RAM(b10 상태)의 '{%s}는…' → '는'(88A6) 을 마커 $1C + {~}(7E) 로 포크
local hits = {}
for a = 0x100000, 0x10FFFF - 8 do
  if memory.read_u8(a, BUS) == 0x25 then
    local ok = true
    for k = 2, #pat do
      if memory.read_u8(a + k - 1, BUS) ~= pat[k] then ok = false; break end
    end
    if ok then hits[#hits+1] = a end
  end
end
say("template hits: " .. #hits)
for _, a in ipairs(hits) do
  local t = {}
  for k = 0, 15 do t[#t+1] = string.format("%02X", memory.read_u8(a + k, BUS)) end
  say(string.format("  @%06X %s", a, table.concat(t, " ")))
  memory.write_u8(a + 2, 0x1C, BUS); memory.write_u8(a + 3, 0x7E, BUS)  -- 는 -> 마커(은/는) + 반칸
  say(string.format("  poked -> %02X %02X (readback)", memory.read_u8(a + 2, BUS), memory.read_u8(a + 3, BUS)))
end
-- 공격: I 를 주기적으로 눌러 전투 진행, 상태 전이·스크린샷 기록
local prev = ""
for f = 1, 720 do
  if f % 45 == 1 then pcall(joypad.set, { I = true }, 1) end
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
  if f % 90 == 0 then pcall(client.screenshot, string.format("%s/josa_poke_%03d.png", OUTDIR, f)) end
end
-- 이름 버퍼 $302E (Main Memory? zp/RAM bank F8) 덤프
local ok, mm = pcall(function()
  local t = {}
  for k = 0, 15 do t[#k+1] = string.format("%02X", memory.read_u8(0x102E + k, "Main Memory")) end
  return table.concat(t, " ")
end)
say("name buffer $302E (Main Memory 0x102E): " .. tostring(ok and mm or "n/a"))
say("done")
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
