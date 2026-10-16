-- b34: 사본 퀵세이브 로드 → 상주 텍스트 뱅크(TurboCD RAM 0x8000-0x9FFF = 디스크 0x89000-0x8AFFF)를 b34 판으로 덮어씀 → 좌우 이동으로 일반 전투 → 메시지 스크린샷
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b34_runtime\]]
local D = "Main Memory"
local function r(a) return memory.read_u8(a, D) end
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "qs.State")
local f = assert(io.open(OUT .. "bank_89000.bin", "rb")); local data = f:read("*a"); f:close()
for i = 1, #data do memory.write_u8(0x8000 + i - 1, data:byte(i), "TurboCD RAM") end
local inb, shots, started = false, 0, 0
for fr = 1, 12000 do
  local pad = {}
  if (fr // 40) % 2 == 0 then pad.Left = true else pad.Right = true end
  if started > 0 and fr - started > 200 and fr % 25 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local b = (r(0x1220) + r(0x1221) + r(0x1222) + r(0x1223)) > 0
  if b and not inb then started = fr end
  inb = b
  if started > 0 and shots < 40 and (fr - started) % 20 == 0 then shots = shots + 1; pcall(client.screenshot, OUT .. string.format("bt_%02d.png", shots)) end
  if shots >= 40 then break end
end
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
