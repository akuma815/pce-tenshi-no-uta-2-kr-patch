-- 초상화 대사 진행 관측 (TAG=b10) — I 를 3프레임 홀드로 반복 입력
local OUT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b11_armchk\adv_b10]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_portrait.State]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUT .. ".log", "w"))
local function rd(a) return memory.read_u8(a, CD) end
local function say(s) log:write(s .. "\n"); log:flush() end
for i = 1, 40 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 10 do emu.frameadvance() end
local prev, armed = "", 0
local shots = 0
for f = 1, 900 do
  local m = f % 45
  if m == 1 or m == 2 or m == 3 then pcall(joypad.set, {{ I = true }}, 1) end
  emu.frameadvance()
  local l = string.format("%02X|%02X|%02X|%02X|%02X",
    rd(0x88F2), rd(0x88F3), rd(0x88F4), rd(0x88F9), rd(0x88FA))
  if l ~= prev then
    prev = l
    say(string.format("f%d %s", f, (l:gsub("|", " "))))
    if rd(0x88F9) ~= 0 then armed = armed + 1 end
  end
  if f % 150 == 0 then
    shots = shots + 1
    client.screenshot(string.format("%s_%d.png", OUT, shots))
  end
end
say("armed_transitions=" .. armed)
say("done")
log:close()
client.exitprogram()
