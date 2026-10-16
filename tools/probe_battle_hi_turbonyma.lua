-- L99(EXP 1600만 1회) 후 다음 전투들에서 전투 블록 덤프 → HP/MP 상위 바이트 위치 확인
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local D = "Main Memory"
local function r(a) return memory.read_u8(a, D) end
local function w(a, v) memory.write_u8(a, v, D) end
pcall(function() client.speedmode(800) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "user_qs1_2151.State")
for i = 0, 3 do w(0x1D67 + i, 0); w(0x1D6B + i, 0x24); w(0x1D6F + i, 0xF4) end
local fh = assert(io.open(OUT .. "bt99.txt", "w"))
for f = 1, 7000 do
  local pad = {}
  if (f // 40) % 2 == 0 then pad.Left = true else pad.Right = true end
  if f % 20 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  if f > 3000 and f % 50 == 0 then
    local b = memory.read_bytes_as_array(0x1210, 0x70, D); local t = {}
    for i = 1, #b do t[i] = string.format("%02X", b[i]) end
    fh:write(f .. " " .. table.concat(t, " ") .. "\n")
  end
end
local b = memory.read_bytes_as_array(0x1D60, 0x40, D); local t = {}
for i = 1, #b do t[i] = string.format("%02X", b[i]) end
fh:write("field " .. table.concat(t, " ") .. "\n"); fh:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
