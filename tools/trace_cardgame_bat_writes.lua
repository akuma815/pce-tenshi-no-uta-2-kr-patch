-- PCEHawk(원본 디스크): 카드 미니게임 화면 전환 중 VDC 데이터 포트($0002/$0003) 쓰기 → 호출 PC 히스토그램 + 앞부분 상세 로그
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\trace]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUT .. "/bat_writes.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local vreg, hist, detail, nw, armed, mawr = 0, {}, {}, 0, false, {}
local function key() local pc = reg("PC"); return string.format("%04X m2=%02X m3=%02X m4=%02X m5=%02X m6=%02X", pc, reg("MPR-2"), reg("MPR-3"), reg("MPR-4"), reg("MPR-5"), reg("MPR-6")) end
event.on_bus_write(function(addr, val)
  vreg = val & 0x1F
end, 0x0000, "vreg", BUS)
local function onw(addr, val)
  if not armed then return end
  if vreg == 0 then
    if addr == 2 then mawr.lo = val else mawr.hi = val; if reg("PC") ~= 0x916B and #detail < 12000 then detail[#detail+1] = string.format("f%d %s MAWR=%02X%02X", emu.framecount(), key(), val, mawr.lo or 0) end end
  elseif vreg == 2 then
    nw = nw + 1
    local k = key(); hist[k] = (hist[k] or 0) + 1
    if reg("PC") ~= 0x9174 and #detail < 12000 then detail[#detail+1] = string.format("f%d %s port=%X val=%02X", emu.framecount(), k, addr, val) end
  end
end
event.on_bus_write(function(a, v) onw(a, v) end, 0x0002, "w2", BUS)
event.on_bus_write(function(a, v) onw(a, v) end, 0x0003, "w3", BUS)
pcall(function() client.speedmode(400) end)
local slot = tonumber(os.getenv("CG_SLOT") or "6")
local p = SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave" .. slot .. ".State"
for i = 1, 30 do emu.frameadvance() end
savestate.load(p)
for i = 1, 5 do emu.frameadvance() end
armed = true
say("loaded slot " .. slot .. " frame=" .. emu.framecount())
pcall(client.screenshot, OUT .. "/s" .. slot .. "_before.png")
local function batsum()
  local b = memory.read_bytes_as_array(0, 4096, "VRAM1"); local h = 0
  for i = 1, #b do h = (h * 31 + b[i]) % 1000000007 end
  return h
end
local presses = {os.getenv("CG_BTN") or "Select", "B2", "B1", "Run"}
for i, btn in ipairs(presses) do
  local f0 = emu.framecount(); local n0 = nw; local h0 = batsum()
  for f = 1, 3 do pcall(joypad.set, {[btn] = true}, 1); emu.frameadvance() end
  for f = 1, 90 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. string.format("/s%d_after_%d_%s.png", slot, i, btn))
  local h1 = batsum()
  say(string.format("press %s at f%d: VWR writes %d  BAT changed=%s", btn, f0, nw - n0, tostring(h0 ~= h1)))
  if h0 ~= h1 then break end
end
say("--- PC histogram (VWR writes) ---")
local ks = {}
for k in pairs(hist) do ks[#ks+1] = k end
table.sort(ks, function(a, b) return hist[a] > hist[b] end)
for _, k in ipairs(ks) do say(string.format("%7d  %s", hist[k], k)) end
say("--- detail (first " .. #detail .. ") ---")
for _, d in ipairs(detail) do say(d) end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
