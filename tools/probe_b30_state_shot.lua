local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b30.TurboNyma.QuickSave1.State")
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUT .. "/b30_qs1.png")
local f = assert(io.open(OUT .. "/b30_qs1_cdram.bin", "wb")); local size = memory.getmemorydomainsize("TurboCD RAM")
for a = 0, size - 1, 4096 do local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, "TurboCD RAM"); local t = {}; for i = 1, n do t[i] = string.char(b[i]) end; f:write(table.concat(t)) end
f:close()
local f2 = assert(io.open(OUT .. "/b30_qs1_wram.bin", "wb")); local b = memory.read_bytes_as_array(0, 8192, "Main Memory"); local t = {}; for i = 1, 8192 do t[i] = string.char(b[i]) end; f2:write(table.concat(t)); f2:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
