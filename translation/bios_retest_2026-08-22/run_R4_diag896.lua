
local out = [[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\f215ea6b-5249-4850-a49a-7d9d5d50dea5\scratchpad\bios_retest]]
for f=1,1500 do
  emu.frameadvance()
  if f==400 or f==800 or f==1500 then
    client.screenshot(out .. [[\R4_diag896_f]] .. f .. [[.png]])
  end
end
client.exitprogram()
