-- b13 회귀 스모크: 사용자 세이브스테이트(b10 TurboNyma) 여러 개를 차례로 로드해
--   각 300프레임 동안 I 를 주기적으로 누르며 armchk 상태 전이·화면을 기록한다.
--   목적 = 전투/메모/메뉴/상태창에서 b13(armchk_v5)이 b10 과 다르게 행동하지 않는지.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b20_runtime]]
local SDIR   = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local STATES = { "diag_battle1", "diag_battle2", "diag_memo", "diag_menu", "diag_status" }
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/smoke_b20.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("KH=%02X FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X",
    rd(0x88FD), rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE))
end
for i = 1, 40 do emu.frameadvance() end
for _, name in ipairs(STATES) do
  local ok, err = pcall(function() savestate.load(SDIR .. name .. ".State") end)
  say(string.format("== %s  load=%s %s", name, tostring(ok), tostring(err or "")))
  for i = 1, 10 do emu.frameadvance() end
  pcall(client.screenshot, string.format("%s/smoke_%s_0.png", OUTDIR, name))
  local prev, armed, serves = "", 0, 0
  for f = 1, 300 do
    if f % 75 == 1 then pcall(joypad.set, { I = true }, 1) end
    emu.frameadvance()
    local l = st()
    if l ~= prev then
      if rd(0x88F9) == 1 and prev:find("FLAG=00") then armed = armed + 1 end
      prev = l; serves = serves + 1
      if serves <= 6 then say(string.format("  f%d %s", f, l)) end
    end
    if f == 150 or f == 300 then pcall(client.screenshot, string.format("%s/smoke_%s_%d.png", OUTDIR, name, f)) end
  end
  say(string.format("  -> transitions=%d armed=%d final %s", serves, armed, st()))
end
say("done")
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
