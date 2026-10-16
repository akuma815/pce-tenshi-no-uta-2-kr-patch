-- 메모 진입 크래시 재현 (TurboNyma, 사용자 세이브 이어하기 → 메뉴 → 메모(5번째) → 항목 결정)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b17_runtime]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/memo_probe.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, CD) end
local function st()
  return string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X | LASTHI=%02X LASTLO=%02X EXPECT=%02X",
    rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE), rd(0x88F2), rd(0x88F3), rd(0x88F5))
end
pcall(function() client.speedmode(400) end)
local function shot(n) pcall(client.screenshot, string.format("%s/memo_%s_f%05d.png", OUTDIR, n, emu.framecount())) end
-- 스크립트: 시작 프레임 기준 상대 프레임 → 버튼
local script = {
  {0, "Run", 3}, {90, "shot", "menu"},
  {120, "Down", 3}, {150, "Down", 3}, {180, "Down", 3}, {210, "Down", 3}, {240, "shot", "memo_sel"},
  {270, "I", 3}, {450, "shot", "memo_in1"}, {600, "shot", "memo_in2"},
  {630, "I", 3}, {810, "shot", "memo_item1"}, {960, "shot", "memo_item2"},
  {990, "II", 3}, {1140, "shot", "back1"}, {1170, "II", 3}, {1320, "shot", "back2"},
}
local started, prev = -1, ""
for f = 1, 9000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f + 300; say("present at f" .. f) end
  if started < 0 then
    if f > 400 and f % 120 < 3 then pad.Run = true; pad.I = true end
  else
    local r = f - started
    for _, e in ipairs(script) do
      if e[2] == "shot" then if r == e[1] then shot(e[3]) end
      elseif r >= e[1] and r < e[1] + e[3] then pad[e[2]] = true end
    end
    if r > 1400 then break end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
