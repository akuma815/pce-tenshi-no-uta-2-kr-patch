-- PCEHawk + b29 디스크(원본 카드): 사용자 s6 스테이트 로드 → Select/B2/B1/Run → 스크린샷 + VRAM1 덤프 (타일 재적재 여부 확인용)
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local log = assert(io.open(OUT .. "/b29_probe.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function dump(dom, path)
  local size = memory.getmemorydomainsize(dom); local f = assert(io.open(path, "wb"))
  for a = 0, size - 1, 4096 do
    local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, dom); local s = {}
    for i = 1, n do s[i] = string.char(b[i]) end
    f:write(table.concat(s))
  end
  f:close()
end
pcall(function() client.speedmode(400) end)
local slot = tonumber(os.getenv("CG_SLOT") or "6")
for i = 1, 30 do emu.frameadvance() end
local ok, err = pcall(savestate.load, SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave" .. slot .. ".State")
say("state load ok=" .. tostring(ok) .. " " .. tostring(err))
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUT .. "/b29_s" .. slot .. "_0.png")
for i, btn in ipairs({"Select", "B2", "B1", "Run"}) do
  for f = 1, 3 do pcall(joypad.set, {[btn] = true}, 1); emu.frameadvance() end
  for f = 1, 90 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/b29_s%d_%d_%s.png", slot, i, btn))
end
dump("VRAM1", OUT .. "/b29_s" .. slot .. "_VRAM1.bin")
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
