-- 부팅 A/V 비교 (2026-10-11 영상 싱크 A/B): 전원 투입부터 같은 입력으로 PROBE_TOTAL 프레임 진행 — 원본·한글판을 같은 조건으로 녹화(오디오는 EmuHawk --dump-type=wave).
-- 입력: PROBE_PRESS(「프레임:버튼,…」, 3프레임 유지). 기록: PROBE_SHOT 프레임마다 스크린샷 + 매 프레임 0x0005·랙 여부(sig.tsv).
local OUT = assert(os.getenv("PROBE_OUT")); local TOTAL = tonumber(os.getenv("PROBE_TOTAL") or "6000"); local SHOT = tonumber(os.getenv("PROBE_SHOT") or "60")
local PRESS = {}
for f, b in (os.getenv("PROBE_PRESS") or ""):gmatch("(%d+):(%a+)") do for k = 0, 2 do PRESS[tonumber(f) + k] = b end end
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local sig = assert(io.open(OUT .. "/sig.tsv", "w"))
for f = 1, TOTAL do
  if PRESS[f] then joypad.set({[PRESS[f]] = true}, 1) end
  emu.frameadvance()
  if f % SHOT == 0 then client.screenshot(OUT .. string.format("/s_%05d.png", f)) end
  sig:write(string.format("%d\t%02X\t%s\n", f, memory.read_u8(0x0005, "Main Memory"), tostring(emu.islagged())));
end
sig:close()
local d = io.open(OUT .. "/done", "w"); d:write("ok"); d:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
