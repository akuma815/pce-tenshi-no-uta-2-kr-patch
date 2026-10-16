-- b13 자동 스모크: 부팅 → 새 게임 → 첫 대사 (일반 대사 ④ 경로 회귀 확인)
-- b10 러너(run_b10_first_dialogue.lua)와 같은 펄스 입력. SaveRAM 없는 상태로 실행할 것.
-- PASS: FLAG=01 & TBANK ∈ 확장 뱅크 관측 + 첫 대사 한글 스크린샷.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b14_runtime]]
local log = assert(io.open(OUTDIR .. [[\firstdlg_poll.tsv]], "w"))
log:write("frame\tFLAG\tTBANK\tCURL\tCURH\tPRESENT\tnote\n"); log:flush()
local CD = "TurboCD RAM"
local F_FLAG, F_TBANK, F_CURL, F_CURH, F_PRESENT = 0x88F9, 0x88FA, 0x88FB, 0x88FC, 0x88FE
local function ext_ok(tb) return (tb >= 0x20 and tb <= 0x3F) or (tb >= 0x44 and tb <= 0x5F) end
pcall(function() client.speedmode(800) end)
local prev, shots, serve_frames, last_shot = "", 0, 0, -999
local TOTAL = 9000
for f = 1, TOTAL do
  if f > 300 and f % 120 < 3 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  emu.frameadvance()
  local flag, tb = memory.read_u8(F_FLAG, CD), memory.read_u8(F_TBANK, CD)
  local cl, ch, pr = memory.read_u8(F_CURL, CD), memory.read_u8(F_CURH, CD), memory.read_u8(F_PRESENT, CD)
  local note = ""
  if flag == 1 and ext_ok(tb) then
    serve_frames = serve_frames + 1
    if shots < 8 and f - last_shot >= 90 then
      shots = shots + 1; last_shot = f
      client.screenshot(string.format("%s\\firstdlg_serve_%02d_f%05d.png", OUTDIR, shots, f))
      note = "SERVE_SHOT"
    end
  end
  local line = string.format("%02X|%02X|%02X", flag, tb, pr)
  if line ~= prev or note ~= "" then
    prev = line
    log:write(string.format("%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n", f, flag, tb, cl, ch, pr, note)); log:flush()
  end
  if f % 1500 == 0 then client.screenshot(string.format("%s\\firstdlg_walk_f%05d.png", OUTDIR, f)) end
end
log:write(string.format("done frames=%d serve_frames=%d shots=%d\n", TOTAL, serve_frames, shots))
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
