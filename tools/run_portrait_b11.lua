-- 필드 초상화 대사 판정 (TAG=b11): 스테이트 로드 → 스크린샷 + armchk 폴링
local OUT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b11_armchk\portrait_b11]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_portrait_b11.State]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUT .. ".log", "w"))
local function rd(a) return memory.read_u8(a, CD) end
local function say(s) log:write(s .. "\n"); log:flush() end
for i = 1, 40 do emu.frameadvance() end
local ok, err = pcall(function() savestate.load(STATE) end)
say("state load: " .. tostring(ok) .. " " .. tostring(err))
for i = 1, 10 do emu.frameadvance() end
client.screenshot(OUT .. "_0.png")
say(string.format("t0 PTRL=%02X PTRH=%02X STREAM=%02X FLAG=%02X TBANK=%02X",
  rd(0x88F2), rd(0x88F3), rd(0x88F4), rd(0x88F9), rd(0x88FA)))
local prev = ""
for f = 1, 260 do
  if f % 60 == 1 then pcall(joypad.set, {{ I = true }}, 1) end
  emu.frameadvance()
  local l = string.format("%02X|%02X|%02X|%02X", rd(0x88F2), rd(0x88F3), rd(0x88F4), rd(0x88F9))
  if l ~= prev then prev = l; say(string.format("f%d %s", f, (l:gsub("|", " ")))) end
  if f == 90 then client.screenshot(OUT .. "_1.png") end
  if f == 200 then client.screenshot(OUT .. "_2.png") end
end
say("done")
log:close()
client.exitprogram()
