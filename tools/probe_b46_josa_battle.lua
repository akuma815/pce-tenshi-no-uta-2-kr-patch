-- b46 조사 경로 실행 확인 (2026-10-11): 전투 중 퀵세이브(PROBE_STATE) 로드 → 엔진 창 코드($C737-$C8C7)를 b46 디스크 바이트(PROBE_BANKFILE 파일)로 교체
-- → 좌우 이동으로 일반 전투 유도 + I 반복 입력해 전투 메시지 진행 → 조사 서브(FLAG=1, TBANK=디코더 뱅크) 관측 + 스크린샷. tools/run_focused_probe.ps1 로 실행.
local OUT = assert(os.getenv("PROBE_OUT"))
local STATE = assert(os.getenv("PROBE_STATE"))
local HEXF = assert(os.getenv("PROBE_BANKFILE"))
local DEC = tonumber(os.getenv("PROBE_DEC_BANK") or "21")
local FOCUS_FLAG = [[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\4810c544-ca01-4c35-9ec3-049a276c76c9\scratchpad\focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/josa.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
pcall(function() client.speedmode(200) end)
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE)
emu.frameadvance()
local bf = assert(io.open(HEXF, "rb")); local data = bf:read("*a"); bf:close()
local n = #data
for i = 1, n do memory.write_u8(0x8000 + i - 1, data:byte(i), "TurboCD RAM") end   -- 상주 텍스트·창 뱅크 = 디스크 0x89000-0x8AFFF (b34 방식)
say("window bytes patched: " .. n)
local josa, last, inb, started = 0, "", false, 0
local function r(a) return memory.read_u8(a, "Main Memory") end
for f = 1, 12000 do
  local btn = {}
  if (f // 40) % 2 == 0 then btn.Left = true else btn.Right = true end      -- 좌우로만 이동(사용자 지시)
  if started > 0 and f - started > 200 and f % 25 < 3 then btn.I = true end
  joypad.set(btn, 1)
  emu.frameadvance()
  local b = (r(0x1220) + r(0x1221) + r(0x1222) + r(0x1223)) > 0          -- 전투 판정(b34 프로브와 같음)
  if b and not inb then started = f; say("battle start f" .. f) end
  inb = b
  local flag, tb = cd(0x88F9), cd(0x88FA)
  local s = string.format("FLAG=%02X TBANK=%02X CUR=%02X%02X", flag, tb, cd(0x88FC), cd(0x88FB))
  if s ~= last then say("f" .. f .. " " .. s); last = s end
  if flag == 1 and tb == DEC then josa = josa + 1; client.screenshot(string.format("%s/josa_%05d.png", OUT, f)) end
  if started > 0 and (f - started) % 20 == 0 then client.screenshot(string.format("%s/bt_%05d.png", OUT, f)) end
  if started > 0 and f - started > 1600 then break end
end
say("josa_serve_frames=" .. josa); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
