-- 상태 로드 후 입력이 게임에 도달하는가 (최소 진단)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local log = assert(io.open(OUTDIR .. "/input_test.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local nhit = 0
for i = 1, 20 do emu.frameadvance() end
say("load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
event.on_bus_exec(function() nhit = nhit + 1 end, 0x967E, "t", "System Bus")
pcall(client.setscreenshotosd, false)
pcall(client.speedmode, 100)
pcall(client.screenshot, OUTDIR .. "/in_00_base.png")

local modes = {
  { name = "B1_hold30",  fn = function(f) return { B1 = (f % 60 < 30) } end },
  { name = "Run_hold30", fn = function(f) return { Run = (f % 60 < 30) } end },
  { name = "B2_hold30",  fn = function(f) return { B2 = (f % 60 < 30) } end },
  { name = "all_hold8",  fn = function(f) return { B1 = (f % 24 < 8), B2 = (f % 24 < 8), Run = (f % 24 < 8) } end },
}
for mi, m in ipairs(modes) do
  local start = nhit
  for f = 1, 300 do
    pcall(joypad.set, m.fn(f), 1)
    emu.frameadvance()
  end
  pcall(client.screenshot, string.format("%s/in_%02d_%s.png", OUTDIR, mi, m.name))
  say(string.format("%-11s -> 렌더 호출 %d 건 (누적 %d)", m.name, nhit - start, nhit))
end
say("done nhit=" .. nhit)
log:close()
if client.exit then pcall(client.exit) end
