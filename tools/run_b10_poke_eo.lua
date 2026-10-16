-- EA 후보 실증: 상태창 템플릿 전체(157B)를 후보 인코딩으로 교체 후 재진입
-- 후보 = 헤더 {~}14→13(이름 반 칸 좌측) + 민첩 줄 {~}16(두 정렬), 총량 불변
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10_status_diag_2026-08-29]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_menu.State]]
local BUS = "System Bus (21 bit)"
local START = 0x109D22

local f = assert(io.open(OUTDIR .. [[\candidate_EO.bin]], "rb"))
local cand = f:read("*a")
f:close()
assert(#cand == 157, #cand)

local log = assert(io.open(OUTDIR .. [[\poke_eo.log]], "w"))
for i = 1, 40 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 10 do emu.frameadvance() end
for i = 1, #cand do
  memory.write_u8(START + i - 1, string.byte(cand, i), BUS)
end
local ok = true
for i = 1, #cand do
  if memory.read_u8(START + i - 1, BUS) ~= string.byte(cand, i) then ok = false end
end
log:write("poke 157B " .. (ok and "OK" or "MISMATCH") .. "\n")
log:flush()
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for i = 1, 59 do emu.frameadvance() end
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for i = 1, 139 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\poke_EO.png]])
log:write("shot\n")
log:close()
client.exitprogram()
