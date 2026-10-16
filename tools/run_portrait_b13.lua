-- b13 판정: TurboNyma + b13 빌드 + diag_portrait.State(b10 에서 저장, 디스크 레이아웃 동일)
--   스테이트는 초상화 대사 레코드 **중간**(페이지 구분 뒤)에서 저장돼 있어 그 레코드는
--   무장 대상이 아니다. I 로 다음 페이지/다음 레코드로 넘기면서 armchk 스크래치
--   (FLAG/TBANK/CURL/CURH, KH) 가 채워지는지 + 화면이 한글인지 본다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b13_fetch_trace]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait.State]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. "/portrait_b13.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end
local function rd(a) return memory.read_u8(a, CD) end
-- 엔진 RAM $C8xx ↔ TurboCD RAM 0x88xx (b9 실측 매핑)
local function st()
  return string.format("KH=%02X FLAG=%02X TBANK=%02X CUR=%02X%02X PRESENT=%02X",
    rd(0x88FD), rd(0x88F9), rd(0x88FA), rd(0x88FC), rd(0x88FB), rd(0x88FE))
end
for i = 1, 40 do emu.frameadvance() end
local ok, err = pcall(function() savestate.load(STATE) end)
say("state load: " .. tostring(ok) .. " " .. tostring(err))
for i = 1, 10 do emu.frameadvance() end
pcall(client.screenshot, OUTDIR .. "/portrait_b13_0.png")
say("t0 " .. st())
local prev, armed = "", 0
for f = 1, 900 do
  if f % 75 == 1 then pcall(joypad.set, { I = true }, 1) end
  emu.frameadvance()
  local l = st()
  if l ~= prev then
    prev = l; say(string.format("f%d %s", f, l))
    if rd(0x88F9) == 1 then armed = armed + 1 end
  end
  if f % 150 == 0 then pcall(client.screenshot, string.format("%s/portrait_b13_%d.png", OUTDIR, f)) end
end
say("done armed_transitions=" .. armed)
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
