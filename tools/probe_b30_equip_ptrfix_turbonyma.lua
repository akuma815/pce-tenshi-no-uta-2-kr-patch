-- TurboNyma + b30 QuickSave1(장비 창): 메뉴 모듈 RAM 의 祈りの盾 포인터를 CDC2 로 포크 → 커서 이동으로 목록 재묘사 → 스크린샷
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local log = assert(io.open(OUT .. "/b30_equip.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local D = "TurboCD RAM"
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b30.TurboNyma.QuickSave1.State")
for i = 1, 5 do emu.frameadvance() end
say(string.format("table entry17 before: %02X %02X", memory.read_u8(0x8A2A, D), memory.read_u8(0x8A2B, D)))
memory.write_u8(0x8A2A, 0xC2, D); memory.write_u8(0x8A2B, 0xCD, D)
say(string.format("after: %02X %02X", memory.read_u8(0x8A2A, D), memory.read_u8(0x8A2B, D)))
pcall(client.screenshot, OUT .. "/b30_equip_0.png")
local seq = {{"II", 3}, {nil, 60}, {"I", 3}, {nil, 60}, {"Down", 3}, {nil, 40}, {"II", 3}, {nil, 60}, {"Down", 3}, {nil, 40}, {"I", 3}, {nil, 60}}
for i, step in ipairs(seq) do
  for f = 1, step[2] do if step[1] then pcall(joypad.set, {[step[1]] = true}, 1) end; emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/b30_equip_%d.png", i))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
