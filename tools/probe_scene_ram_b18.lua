-- diag_battle1.State 의 씬/엔진 RAM 에서 {%s} 템플릿 위치와 도메인 목록을 기록한다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b18_runtime]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_battle1.State]]
local BUS = "System Bus (21 bit)"
local log = assert(io.open(OUTDIR .. "/scene_ram_probe.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
for i = 1, 40 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
local names = memory.getmemorydomainlist()
local t = {}
for i = 0, #names do if names[i] then t[#t+1] = names[i] .. "(" .. tostring(memory.getmemorydomainsize(names[i])) .. ")" end end
say("domains: " .. table.concat(t, " | "))
local function scan(lo, hi, tag, limit)
  local n = 0
  for a = lo, hi - 16 do
    if memory.read_u8(a, BUS) == 0x25 and memory.read_u8(a + 1, BUS) == 0x73 then
      n = n + 1
      if n <= limit then
        local c = {}
        for k = -2, 13 do c[#c+1] = string.format("%02X", memory.read_u8(a + k, BUS)) end
        say(string.format("  %s @%06X: %s", tag, a, table.concat(c, " ")))
      end
    end
  end
  say(tag .. " total: " .. n)
end
scan(0xD0000, 0xFFFFF, "scene", 40)
scan(0x100000, 0x10FFFF, "engine", 10)
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
