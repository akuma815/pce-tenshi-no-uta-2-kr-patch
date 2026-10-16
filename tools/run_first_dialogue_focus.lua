-- 공용 자동 스모크 (2026-10-11): 부팅 → 새 게임 → 첫 대사. tools/run_focused_probe.ps1 과 함께 쓴다.
-- Lua 콘솔이 뜨며 메인 창이 비활성화되므로(입력이 안 먹음), 외부에서 메인 창을 선택하고 신호 파일을 만들 때까지 일시정지한다.
-- 입력: 프레임 300 부터 120프레임마다 3프레임 — 1500 전에는 Run 만(BIOS·타이틀), 이후 I 만(새 게임·대사 진행).
--   (Run+I+II 동시 입력은 BIOS 화면에서 먹지 않았다 — 2026-10-11 실측)
-- 출력 폴더 = 환경변수 PROBE_OUT. 같은 입력이므로 빌드끼리 같은 프레임 스크린샷을 픽셀 비교할 수 있다(세이브 없는 상태로).
local OUTDIR = assert(os.getenv("PROBE_OUT"), "PROBE_OUT 미지정")
local FOCUS_FLAG = [[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\4810c544-ca01-4c35-9ec3-049a276c76c9\scratchpad\focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUTDIR .. "\\firstdlg_poll.tsv", "w"))
log:write("frame\tFLAG\tTBANK\tCURL\tCURH\tPRESENT\tDBANK\tnote\n"); log:flush()
local CD = "TurboCD RAM"
local F_FLAG, F_TBANK, F_CURL, F_CURH, F_PRESENT, F_DBANK = 0x88F9, 0x88FA, 0x88FB, 0x88FC, 0x88FE, 0x88F8
pcall(function() client.speedmode(800) end)
local prev, shots, serve_frames, dict_frames, bad = "", 0, 0, 0, 0
local TOTAL = 9000
for f = 1, TOTAL do
  if f > 300 and f % 120 < 3 then
    if f < 1500 then joypad.set({ Run = true }, 1) else joypad.set({ I = true }, 1) end
  end
  emu.frameadvance()
  local flag, tb = memory.read_u8(F_FLAG, CD), memory.read_u8(F_TBANK, CD)
  local cl, ch, pr, db = memory.read_u8(F_CURL, CD), memory.read_u8(F_CURH, CD), memory.read_u8(F_PRESENT, CD), memory.read_u8(F_DBANK, CD)
  local note = ""
  if flag == 1 or flag == 2 then
    serve_frames = serve_frames + 1
    if flag == 2 then dict_frames = dict_frames + 1 end
    if tb < 0x20 or tb > 0x3F or (flag == 2 and (db < 0x20 or db > 0x3F)) then bad = bad + 1; note = "BAD_BANK" end
  end
  local line = string.format("%02X|%02X|%02X|%02X", flag, tb, pr, db)
  if line ~= prev or note ~= "" then
    prev = line
    log:write(string.format("%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n", f, flag, tb, cl, ch, pr, db, note)); log:flush()
  end
  if f % 300 == 0 then shots = shots + 1; client.screenshot(string.format("%s/f%05d.png", OUTDIR, f)) end
end
log:write(string.format("done frames=%d serve_frames=%d dict_frames=%d bad=%d shots=%d\n", TOTAL, serve_frames, dict_frames, bad, shots))
log:close()
client.exitprogram()
