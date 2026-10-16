-- TurboNyma + b29: 사용자 TurboNyma 퀵세이브 로드 → 위치 스크린샷 + PRESENT/FLAG 폴링 + B1 수회
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local log = assert(io.open(OUT .. "/b29_tn_state.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
local function st() return string.format("PRESENT=%02X FLAG=%02X TBANK=%02X", cd(0x88FE), cd(0x88F9), cd(0x88FA)) end
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
local ok, err = pcall(savestate.load, SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b29.TurboNyma.QuickSave1.State")
say("load ok=" .. tostring(ok) .. " " .. tostring(err))
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUT .. "/b29_tn_0.png"); say("after load: " .. st())
for i = 1, 3 do
  for f = 1, 3 do pcall(joypad.set, {B1 = true}, 1); emu.frameadvance() end
  for f = 1, 120 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. "/b29_tn_" .. i .. ".png"); say("press " .. i .. ": " .. st())
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
