-- 사용자 스테이트(메모 항목 커서, 결정 전) → I 1회 → 프레임별 훅/스트림 상태 기록
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b23_runtime\userstate]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b23.TurboNyma.QuickSave1.State]]
local CD, MM = "TurboCD RAM", "Main Memory"
local log = assert(io.open(OUTDIR .. "/probe.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, CD) end
local function z(a) return memory.read_u8(a, MM) end          -- $2000+a
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X KH=%02X IBANK=%02X | LASTHI=%02X LASTLO=%02X EXPECT=%02X | zp55=%02X zp54=%02X zp53=%02X zp52=%02X zp4C=%02X zp4B=%02X 2E69=%02X 22D0=%02X 2D80=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE), rd(0x88FD), rd(0x88F6), rd(0x88F2), rd(0x88F3), rd(0x88F5),
    z(0x55), z(0x54), z(0x53), z(0x52), z(0x4C), z(0x4B), z(0xE69), z(0x2D0), z(0xD80))
end
for i = 1, 30 do emu.frameadvance() end
say("load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
pcall(client.screenshot, OUTDIR .. "/u_load.png")
say("t0 " .. st())
local prev = ""
for f = 1, 900 do
  local pad = {}
  if f >= 10 and f < 13 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
  if f % 30 == 0 then pcall(client.screenshot, string.format("%s/u_f%03d.png", OUTDIR, f)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
