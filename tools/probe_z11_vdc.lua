-- VDC 포트 사용 실태 조사: 어느 주소로 어떤 레지스터를 선택하는가
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local log = assert(io.open(OUTDIR .. "/vdc.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end

local selhist, addrhist = {}, {}
local sel = 0
local r7lo, r7hi, r8lo, r8hi = -1, -1, -1, -1

local function val_of(v)
  if type(v) == "number" then return v end
  return emu.getregister("A") or 0
end

-- VDC 포트와 그 미러들을 폭넓게 감시
local ports = {0x0000, 0x0001, 0x0002, 0x0003, 0x0400, 0x0402, 0x0403}
for _, p in ipairs(ports) do
  event.on_bus_write(function(addr, v)
    local x = val_of(v)
    addrhist[p] = (addrhist[p] or 0) + 1
    if p == 0x0000 or p == 0x0400 then
      sel = x % 32
      selhist[sel] = (selhist[sel] or 0) + 1
    elseif p == 0x0002 or p == 0x0402 then
      if sel == 7 then r7lo = x elseif sel == 8 then r8lo = x end
    elseif p == 0x0003 or p == 0x0403 then
      if sel == 7 then r7hi = x elseif sel == 8 then r8hi = x end
    end
  end, p, "vdc" .. p, "System Bus")
end

pcall(client.speedmode, 100)
for f = 1, 900 do
  pcall(joypad.set, { B1 = (f % 60 < 30) }, 1)
  emu.frameadvance()
end

local ks = {}
for k in pairs(selhist) do ks[#ks+1] = k end
table.sort(ks)
local parts = {}
for _, k in ipairs(ks) do parts[#parts+1] = string.format("R%d:%d", k, selhist[k]) end
say("선택된 VDC 레지스터 분포: " .. table.concat(parts, "  "))
local ap = {}
for _, p in ipairs(ports) do ap[#ap+1] = string.format("$%04X:%d", p, addrhist[p] or 0) end
say("포트별 쓰기 횟수: " .. table.concat(ap, "  "))
say(string.format("R7(BXR) lo=%d hi=%d -> %s", r7lo, r7hi,
    (r7lo >= 0) and tostring(r7lo + math.max(r7hi,0)*256) or "미관측"))
say(string.format("R8(BYR) lo=%d hi=%d -> %s", r8lo, r8hi,
    (r8lo >= 0) and tostring(r8lo + math.max(r8hi,0)*256) or "미관측"))
log:close()
if client.exit then pcall(client.exit) end
