-- b20 전투 중 훅 상태 실측 (TurboNyma, 사용자 세이브 이어하기 → 걷기 → 전투)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b23_runtime]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/battle_probe.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X | LASTHI=%02X LASTLO=%02X EXPECT=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE), rd(0x88F2), rd(0x88F3), rd(0x88F5))
end
pcall(function() client.speedmode(400) end)
local prev, shots, pending = "", 0, -1
-- 슬롯 1(야외, 전투 가능) 고정: 로드 목록이 그려지면(LASTHI 가 00→텍스트, PRESENT 아직 0) Up → I.
local started, listed, prev_hi = -1, -1, 0
for f = 1, 14000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f end
  if listed < 0 and started < 0 and rd(0x88F2) ~= 0x00 and rd(0x88F2) ~= 0xFF then listed = f; say("load list at f" .. f) end
  if started < 0 then
    if listed < 0 then
      if f > 400 and f % 120 < 3 then pad.Run = true end
    else
      local r = f - listed
      -- 목록 텍스트가 먼저 찍히고 BRAM 이름·커서는 한참 뒤에 채워진다(실측: +150 프레임엔 아직 「용량부족」)
      if r >= 500 and r < 510 then pad.Up = true end
      if r == 560 then pcall(client.screenshot, OUTDIR .. "/bprobe_loadlist.png") end
      if r >= 600 and r < 610 then pad.I = true end
      if r >= 1000 and r % 120 < 3 then pad.I = true end    -- 안전망
    end
  elseif f - started >= 300 then
    local ph = ((f - started) // 150) % 4
    if ph == 0 then pad.Left = true elseif ph == 1 then pad.Up = true elseif ph == 2 then pad.Right = true else pad.Down = true end
    if f % 40 == 0 then pad.II = true end
    if f % 200 == 0 then pad.I = true end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then
    prev = l; say(string.format("f%d %s", f, l))
    if rd(0x88F9) == 0x01 and shots < 40 then pending = f + 24 end   -- 조사 서브 직후 24프레임 뒤 스크린샷
  end
  if pending == f then
    shots = shots + 1; pcall(client.screenshot, string.format("%s/bprobe_%02d_f%05d.png", OUTDIR, shots, f))
  end
  if f % 1000 == 0 then pcall(client.screenshot, string.format("%s/bprobe_walk_f%05d.png", OUTDIR, f)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
