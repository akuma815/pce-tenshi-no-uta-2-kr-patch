local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime\callers_qs]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave2.State]]
local BUS = "System Bus"
local tsv = assert(io.open(OUTDIR .. "/qs2.tsv", "w"))
local function rd(a) return memory.read_u8(a, BUS) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local cur, getfnt, inner = nil, 0, false
local function flush() if cur then tsv:write(string.format("%d\t%s\t%04X\t%02X\t%d\n", cur.f, cur.k, cur.r, rd(0x2D80), getfnt)) end cur, getfnt = nil, 0 end
local function start(k) local s = reg("S"); local r = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256; flush(); cur = { f = emu.framecount(), k = k, r = r } end
event.on_bus_exec(function() start("v"); inner = true end, 0x4036, "vec", BUS)
event.on_bus_exec(function() if inner then inner = false else start("d") end end, 0x4284, "disp", BUS)
event.on_bus_exec(function() getfnt = getfnt + 1 end, 0x967E, "getfnt", BUS)
for i = 1, 30 do emu.frameadvance() end
local ok = pcall(function() savestate.load(STATE) end)
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUTDIR .. "/qs2" .. "_load_" .. tostring(ok) .. ".png")
for f = 1, 900 do
  local pad = {}
  if f % 45 < 3 then pad.B1 = true end
  pcall(joypad.set, pad, 1); emu.frameadvance()
  if f % 300 == 0 then pcall(client.screenshot, string.format("%s/qs2" .. "_f%03d.png", OUTDIR, f)) end
end
flush(); tsv:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
