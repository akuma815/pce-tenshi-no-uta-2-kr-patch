-- EC 후보: 민첩 줄만 제자리 21B 교체 — 민첩 {~} 　 {~}x13 두
-- (8140 이 원본과 동일한 짝수 오프셋, 헤더/지능/운 줄 무변경)
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10_status_diag_2026-08-29]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_menu.State]]
local BUS = "System Bus (21 bit)"
local ADDR = 0x109D7B
local BYTES = { 0x8C, 0x7E, 0x90, 0xEF, 0x7E, 0x81, 0x40,
                0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E,
                0x7E, 0x7E, 0x7E, 0x89, 0xE1 }

local log = assert(io.open(OUTDIR .. [[\poke_ec.log]], "w"))
for i = 1, 40 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 10 do emu.frameadvance() end
for i, v in ipairs(BYTES) do memory.write_u8(ADDR + i - 1, v, BUS) end
local ok = true
for i, v in ipairs(BYTES) do
  if memory.read_u8(ADDR + i - 1, BUS) ~= v then ok = false end
end
log:write("poke " .. #BYTES .. "B " .. (ok and "OK" or "MISMATCH") .. "\n")
log:flush()
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for i = 1, 59 do emu.frameadvance() end
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for i = 1, 139 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\poke_EC_min_tilde_space.png]])
log:write("shot\n")
log:close()
client.exitprogram()
