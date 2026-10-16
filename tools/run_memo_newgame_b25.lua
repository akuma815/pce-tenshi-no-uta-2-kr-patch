-- 새 게임(SaveRAM 없음) → 도입 대사 I 넘김 → 메뉴 → 메모(5번째) → 항목 결정 → 20프레임마다 스크린샷
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b25_runtime\memonew]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/memo_new.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X | LASTHI=%02X LASTLO=%02X EXPECT=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE), rd(0x88F2), rd(0x88F3), rd(0x88F5))
end
pcall(function() client.speedmode(400) end)
local started, prev, n = -1, "", 0
local script = {}
local B = 3000   -- 도입 대사 뒤 메뉴
for k = 0, 4 do
  local t = B + k * 1200
  script[#script+1] = {t, "Run"}; script[#script+1] = {t+120, "Down"}; script[#script+1] = {t+150, "Down"}
  script[#script+1] = {t+180, "Down"}; script[#script+1] = {t+210, "Down"}; script[#script+1] = {t+300, "I"}
  script[#script+1] = {t+500, "I"}; script[#script+1] = {t+800, "I"}; script[#script+1] = {t+1000, "II"}; script[#script+1] = {t+1060, "II"}; script[#script+1] = {t+1120, "II"}
end
for f = 1, 16000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f; say("present f" .. f) end
  if started < 0 then
    if f > 400 and f % 120 < 3 then pad.Run = true; pad.I = true; pad.II = true end
  else
    local r = f - started
    if r < B and r % 60 < 3 then pad.I = true end
    for _, e in ipairs(script) do if r >= e[1] and r < e[1] + 4 then pad[e[2]] = true end end
    if r >= B and r % 20 == 0 then n = n + 1; pcall(client.screenshot, string.format("%s/s_%04d_f%05d.png", OUTDIR, n, f)) end
    if r > B + 6000 then break end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
