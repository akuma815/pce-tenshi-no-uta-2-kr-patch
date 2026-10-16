-- PCEHawk: QuickSave1..10 각각 로드 → VRAM1/VCEPalette/Main Memory/TurboCD RAM 덤프 + 스크린샷
local ROOT  = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT   = ROOT .. [[\translation\cardgame\vram]]
local SDIR  = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local log = assert(io.open(OUT .. "/dump_pcehawk.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local names = memory.getmemorydomainlist(); local t = {}
for i = 0, #names do if names[i] then t[#t+1] = names[i] .. "(" .. tostring(memory.getmemorydomainsize(names[i])) .. ")" end end
say("domains: " .. table.concat(t, " | "))
local function dump(dom, path)
  local ok, size = pcall(memory.getmemorydomainsize, dom)
  if not ok or not size then say("  no domain " .. dom); return end
  local f = assert(io.open(path, "wb")); local step = 4096
  for a = 0, size - 1, step do
    local n = math.min(step, size - a); local bytes = memory.read_bytes_as_array(a, n, dom); local s = {}
    for i = 1, n do s[i] = string.char(bytes[i]) end
    f:write(table.concat(s))
  end
  f:close(); say("  " .. dom .. " " .. size .. "B")
end
for i = 1, 30 do emu.frameadvance() end
for slot = 1, 10 do
  local p = SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave" .. slot .. ".State"
  local fh = io.open(p, "rb")
  if fh then
    fh:close()
    local ok = pcall(function() savestate.load(p) end)
    for i = 1, 3 do emu.frameadvance() end
    say("slot " .. slot .. " load=" .. tostring(ok))
    local tag = "s" .. slot
    pcall(client.screenshot, OUT .. "/" .. tag .. ".png")
    for _, dom in ipairs({"VRAM1", "VCEPalette", "Main Memory", "TurboCD RAM", "Super System Card RAM"}) do
      dump(dom, string.format("%s/%s_%s.bin", OUT, tag, (dom:gsub("[^%w]", "_"))))
    end
    -- VDC 레지스터는 도메인이 없으므로 BAT 크기는 덤프 분석에서 추정
  end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
