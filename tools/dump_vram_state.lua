-- 세이브 스테이트 → VRAM/VCE/BAT 덤프 (TurboNyma). 인자: STATE 경로는 아래 상수, OUT 폴더.
local ROOT  = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT   = ROOT .. [[\translation\cardgame\vram]]
local STATE = ROOT .. [[\BizHawk-master\output\PC Engine\State\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b28.TurboNyma.QuickSave1.State]]
local TAG = "qs1"
local log = assert(io.open(OUT .. "/dump_" .. TAG .. ".log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
for i = 1, 30 do emu.frameadvance() end
say("load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 3 do emu.frameadvance() end
local names = memory.getmemorydomainlist(); local t = {}
for i = 0, #names do if names[i] then t[#t+1] = names[i] .. "(" .. tostring(memory.getmemorydomainsize(names[i])) .. ")" end end
say("domains: " .. table.concat(t, " | "))
local function dump(dom, path)
  local ok, size = pcall(memory.getmemorydomainsize, dom)
  if not ok or not size then say("no domain " .. dom); return end
  local f = assert(io.open(path, "wb"))
  local step = 4096
  for a = 0, size - 1, step do
    local n = math.min(step, size - a)
    local bytes = memory.read_bytes_as_array(a, n, dom)
    local s = {}
    for i = 1, n do s[i] = string.char(bytes[i]) end
    f:write(table.concat(s))
  end
  f:close(); say("dumped " .. dom .. " " .. size .. "B -> " .. path)
end
for _, dom in ipairs({"VRAM1", "VRAM", "VCEPalette", "Main Memory", "TurboCD RAM"}) do
  dump(dom, string.format("%s/%s_%s.bin", OUT, TAG, (dom:gsub("[^%w]", "_"))))
end
pcall(client.screenshot, OUT .. "/" .. TAG .. ".png")
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
