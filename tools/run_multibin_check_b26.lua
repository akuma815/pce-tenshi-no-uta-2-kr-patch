local OUT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b26_runtime\multibin]]
local CD = "TurboCD RAM"
local function rd(a) return memory.read_u8(a, CD) end
pcall(function() client.speedmode(400) end)
local started, n = -1, 0
local log = assert(io.open(OUT .. "/log.txt", "w"))
for f = 1, 7000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f; log:write("present f" .. f .. "\n") end
  if started < 0 then if f > 400 and f % 120 < 3 then pad.Run = true; pad.I = true; pad.II = true end
  else if (f - started) % 60 < 3 then pad.I = true end end
  pcall(joypad.set, pad, 1); emu.frameadvance()
  if f % 500 == 0 then pcall(client.screenshot, string.format("%s/mb_f%05d.png", OUT, f)) end
end
log:write("done\n"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
