-- TurboNyma: 사본 스테이트 로드 → Main Memory·TurboCD RAM 덤프 + 스크린샷 (스테이트 원본 슬롯은 건드리지 않음)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local log = assert(io.open(OUT .. "probe.log", "w"))
local function say(x) log:write(tostring(x) .. "\n"); log:flush() end
say("start")
local function dump(dom, path)
  local size = memory.getmemorydomainsize(dom); local f = assert(io.open(path, "wb"))
  for a = 0, size - 1, 4096 do local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, dom); local t = {}; for i = 1, n do t[i] = string.char(b[i]) end; f:write(table.concat(t)) end
  f:close()
end
for i = 1, 60 do emu.frameadvance() end
local ok, err = pcall(savestate.load, OUT .. "user_qs1_2151.State"); say("load " .. tostring(ok) .. " " .. tostring(err))
for i = 1, 3 do emu.frameadvance() end
pcall(client.screenshot, OUT .. "qs1.png")
for _, d in ipairs({{"Main Memory", "qs1_wram.bin"}, {"TurboCD RAM", "qs1_cdram.bin"}}) do
  local ok2, e2 = pcall(dump, d[1], OUT .. d[2]); say(d[1] .. " " .. tostring(ok2) .. " " .. tostring(e2))
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
