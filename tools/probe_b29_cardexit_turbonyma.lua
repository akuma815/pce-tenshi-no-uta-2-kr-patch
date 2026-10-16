-- TurboNyma + b29 QuickSave1(카드 결과 화면): N 선택(Right→B1) → 필드 복귀 → PRESENT 폴링 + 스크린샷 (도박사 대사가 native 로 가는 이유 조사)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local log = assert(io.open(OUT .. "/b29_cardexit.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
local function st() return string.format("PRESENT=%02X FLAG=%02X TBANK=%02X", cd(0x88FE), cd(0x88F9), cd(0x88FA)) end
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b29.TurboNyma.QuickSave1.State")
for i = 1, 5 do emu.frameadvance() end
local seq = {{"Right", 3}, {nil, 20}, {"I", 3}, {nil, 600}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}}
local last = ""
local f0 = emu.framecount()
for _, step in ipairs(seq) do
  for f = 1, step[2] do
    if step[1] then pcall(joypad.set, {[step[1]] = true}, 1) end
    emu.frameadvance()
    local s = st(); if s ~= last then say(string.format("f%d %s", emu.framecount() - f0, s)); last = s end
    if (emu.framecount() - f0) % 60 == 0 then pcall(client.screenshot, OUT .. string.format("/b29_exit_%04d.png", emu.framecount() - f0)) end
  end
  say(string.format("f%d step %s done", emu.framecount() - f0, tostring(step[1])))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
