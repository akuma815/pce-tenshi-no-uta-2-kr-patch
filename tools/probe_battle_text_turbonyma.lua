-- 사본 스테이트 → 좌우 이동으로 일반 전투 유발 → 전투 시작 메시지 구간 스크린샷 (치트 없음, 원본 슬롯 무수정)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b33_runtime\]]
local D = "Main Memory"
local function r(a) return memory.read_u8(a, D) end
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "qs.State")
local inb, shots, started = false, 0, 0
for f = 1, 9000 do
  local pad = {}
  if (f // 40) % 2 == 0 then pad.Left = true else pad.Right = true end
  if started > 0 and f - started > 400 and f % 20 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local b = (r(0x1220) + r(0x1221) + r(0x1222) + r(0x1223)) > 0
  if b and not inb then started = f end
  inb = b
  if started > 0 and shots < 12 and (f - started) % 30 == 0 then shots = shots + 1; pcall(client.screenshot, OUT .. string.format("bt_%02d.png", shots)) end
  if shots >= 12 then break end
end
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
