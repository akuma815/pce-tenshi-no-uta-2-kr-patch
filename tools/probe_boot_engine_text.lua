-- b33 새로 부팅(퀵세이브 없이) → 일정 프레임 후 TurboCD RAM 0x9800-0x9900 덤프 (전투 템플릿 상주 뱅크가 새 디스크에서 올라오는지)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b33_runtime\]]
for f = 1, 1500 do
  if f > 400 and f % 120 < 3 then pcall(joypad.set, {Run = true}, 1) end
  emu.frameadvance()
end
local b = memory.read_bytes_as_array(0x9800, 0x100, "TurboCD RAM"); local t = {}
for i = 1, #b do t[i] = string.format("%02X", b[i]) end
local fh = assert(io.open(OUT .. "boot_9800.txt", "w")); fh:write(table.concat(t)); fh:close()
pcall(client.screenshot, OUT .. "boot.png")
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
