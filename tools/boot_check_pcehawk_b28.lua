local OUT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b28_runtime\pcehawk]]
for f = 1, 1500 do
  local pad = {}
  if f > 400 and f % 120 < 3 then pad.Run = true end
  pcall(joypad.set, pad, 1); emu.frameadvance()
  if f == 900 or f == 1400 then pcall(client.screenshot, string.format("%s/boot_f%04d.png", OUT, f)) end
end
local names = memory.getmemorydomainlist(); local t = {}
for i = 0, #names do if names[i] then t[#t+1] = names[i] end end
local f = io.open(OUT .. "/domains.txt", "w"); f:write(table.concat(t, " | ")); f:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
