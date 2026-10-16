-- diag_battle*.State 를 PCEHawk 에서 로드 시도 → 성공하면 전투 메시지 진행하며 호출자 기록
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime\callers_diag]]
local SDIR   = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local BUS = "System Bus"
local log = assert(io.open(OUTDIR .. "/diag.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local tsv = assert(io.open(OUTDIR .. "/diag.tsv", "w"))
local function rd(a) return memory.read_u8(a, BUS) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local cur, getfnt, inner, tag = nil, 0, false, "?"
local function flush() if cur then tsv:write(string.format("%s\t%d\t%s\t%04X\t%02X\t%d\n", tag, cur.f, cur.k, cur.r, rd(0x2D80), getfnt)) end cur, getfnt = nil, 0 end
local function start(k) local s = reg("S"); local r = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256; flush(); cur = { f = emu.framecount(), k = k, r = r } end
event.on_bus_exec(function() start("v"); inner = true end, 0x4036, "vec", BUS)
event.on_bus_exec(function() if inner then inner = false else start("d") end end, 0x4284, "disp", BUS)
event.on_bus_exec(function() getfnt = getfnt + 1 end, 0x967E, "getfnt", BUS)
for i = 1, 30 do emu.frameadvance() end
for _, n in ipairs({"diag_battle", "diag_battle1", "diag_battle2", "diag_battle3", "diag_status", "diag_menu"}) do
  tag = n
  local ok, err = pcall(function() savestate.load(SDIR .. n .. ".State") end)
  say(n .. " load=" .. tostring(ok) .. " " .. tostring(err))
  for i = 1, 5 do emu.frameadvance() end
  pcall(client.screenshot, string.format("%s/%s_load.png", OUTDIR, n))
  if ok then
    for f = 1, 600 do
      local pad = {}
      if f % 45 < 3 then pad.B1 = true end
      pcall(joypad.set, pad, 1); emu.frameadvance()
      if f % 200 == 0 then pcall(client.screenshot, string.format("%s/%s_f%03d.png", OUTDIR, n, f)) end
    end
  end
end
flush(); tsv:close(); say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
