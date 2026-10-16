-- 메모 본문 진입 재현: 기본 슬롯(교회) → 대사 I 넘김 → 자동 메모 창 → I 로 항목 결정 → 20프레임마다 스크린샷
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime\memobody]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/memo_body.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X | LASTHI=%02X LASTLO=%02X EXPECT=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE), rd(0x88F2), rd(0x88F3), rd(0x88F5))
end
pcall(function() client.speedmode(400) end)
local started, prev, n = -1, "", 0
for f = 1, 16000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f; say("present f" .. f) end
  if started < 0 then
    if f > 400 and f % 120 < 3 then pad.Run = true; pad.I = true end
  else
    local r = f - started
    if r < 2400 and r % 60 < 3 then pad.I = true end          -- 대사 넘김
    if r >= 2400 and r % 240 < 3 then pad.I = true end        -- 메모 항목 결정/본문 넘김
    if r >= 2400 and r % 240 >= 120 and r % 240 < 123 then pad.II = true end
    if r >= 3000 and r % 20 == 0 then n = n + 1; pcall(client.screenshot, string.format("%s/s_%04d_f%05d.png", OUTDIR, n, f)) end
    if r > 7200 then break end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
