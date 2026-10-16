local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local function dump(dom, path)
  local size = memory.getmemorydomainsize(dom); local f = assert(io.open(path, "wb"))
  for a = 0, size - 1, 4096 do local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, dom); local t = {}; for i = 1, n do t[i] = string.char(b[i]) end; f:write(table.concat(t)) end
  f:close()
end
pcall(function() client.speedmode(400) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "user_qs1_2151.State")
for i = 1, 3 do emu.frameadvance() end
local seq = {{"II", 3, 40, "s0"}, {"I", 3, 60, "s1"}, {"I", 3, 60, "s2"}, {"Right", 3, 40, "s3"}, {"I", 3, 60, "s4"}, {"Down", 3, 40, "s5"}}
for _, s in ipairs(seq) do
  for f = 1, s[2] do pcall(joypad.set, {[s[1]] = true}, 1); emu.frameadvance() end
  for f = 1, s[3] do emu.frameadvance() end
  pcall(client.screenshot, OUT .. s[4] .. ".png")
end
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
