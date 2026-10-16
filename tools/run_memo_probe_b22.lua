-- 메모 진입 크래시 재현 (TurboNyma, 사용자 세이브 이어하기 → 메뉴 → 메모(5번째) → 항목 결정)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime]]
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
local script = {}
-- 교회 슬롯(아윈마을)은 로드 직후 대사 장면 → I 를 60프레임마다 눌러 넘김(0~2400), 60프레임마다 스크린샷
for k = 0, 39 do script[#script+1] = {k * 60, "I", 3} end
for k = 1, 8 do script[#script+1] = {k * 300, "shot", string.format("dlg%02d", k)} end
local B = 2500
script[#script+1] = {B, "Run", 3}; script[#script+1] = {B + 90, "shot", "menu"}
for k = 0, 3 do script[#script+1] = {B + 120 + k * 30, "Down", 3} end
script[#script+1] = {B + 240, "shot", "memo_sel"}
script[#script+1] = {B + 270, "I", 3}; script[#script+1] = {B + 450, "shot", "memo_list"}
script[#script+1] = {B + 480, "I", 3}
for k = 1, 30 do script[#script+1] = {B + 480 + k * 30, "shot", string.format("body%02d", k)} end
for k = 1, 8 do script[#script+1] = {B + 700 + k * 90, "I", 3} end
local started, prev = -1, ""
for f = 1, 12000 do
  local pad = {}
  if started < 0 and rd(0x88FE) == 0x01 then started = f + 300; say("present at f" .. f) end
  if started < 0 then
    -- 슬롯 1 고정: 타이틀은 Run 으로 넘기고(f<=900), 그 뒤엔 I 만 눌러 로드 목록의 기본 커서(1번)를 결정
    if f > 400 and f <= 900 and f % 120 < 3 then pad.Run = true end
    if f > 900 and f % 120 < 3 then pad.I = true end
    if f > 5000 and f % 120 < 3 then pad.Run = true end
  else
    local r = f - started
    for _, e in ipairs(script) do
      if e[2] == "shot" then if r == e[1] then shot(e[3]) end
      elseif r >= e[1] and r < e[1] + e[3] then pad[e[2]] = true end
    end
    if r > 4000 then break end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  local l = st()
  if l ~= prev then prev = l; say(string.format("f%d %s", f, l)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
