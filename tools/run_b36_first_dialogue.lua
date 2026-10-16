-- b36 자동 스모크 (512KB 카드·사전 압축 serve): 부팅 → 새 게임 → 첫 대사.
-- PASS: FLAG=01/02 & TBANK/DBANK ∈ $20-$3F 관측 + 첫 대사 한글 스크린샷. $40 이상 뱅크 관측 = FAIL.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b36_runtime]]
local log = assert(io.open(OUTDIR .. [[\firstdlg_poll.tsv]], "w"))
log:write("frame\tFLAG\tTBANK\tCURL\tCURH\tPRESENT\tDBANK\tnote\n"); log:flush()
local CD = "TurboCD RAM"
local F_FLAG, F_TBANK, F_CURL, F_CURH, F_PRESENT, F_DBANK = 0x88F9, 0x88FA, 0x88FB, 0x88FC, 0x88FE, 0x88F8
pcall(function() client.speedmode(800) end)
local prev, shots, serve_frames, dict_frames, bad, last_shot = "", 0, 0, 0, 0, -999
local TOTAL = 9000
for f = 1, TOTAL do
  if f > 300 and f % 120 < 3 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  emu.frameadvance()
  local flag, tb = memory.read_u8(F_FLAG, CD), memory.read_u8(F_TBANK, CD)
  local cl, ch, pr, db = memory.read_u8(F_CURL, CD), memory.read_u8(F_CURH, CD), memory.read_u8(F_PRESENT, CD), memory.read_u8(F_DBANK, CD)
  local note = ""
  if flag == 1 or flag == 2 then
    serve_frames = serve_frames + 1
    if flag == 2 then dict_frames = dict_frames + 1 end
    if tb < 0x20 or tb > 0x3F or (flag == 2 and (db < 0x20 or db > 0x3F)) then bad = bad + 1; note = "BAD_BANK" end
    if shots < 10 and f - last_shot >= 90 then
      shots = shots + 1; last_shot = f
      client.screenshot(string.format("%s/firstdlg_serve_%02d_f%05d.png", OUTDIR, shots, f))
      note = note .. "SHOT"
    end
  end
  local line = string.format("%02X|%02X|%02X|%02X", flag, tb, pr, db)
  if line ~= prev or note ~= "" then
    prev = line
    log:write(string.format("%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n", f, flag, tb, cl, ch, pr, db, note)); log:flush()
  end
  if f % 1500 == 0 then client.screenshot(string.format("%s/firstdlg_walk_f%05d.png", OUTDIR, f)) end
end
log:write(string.format("done frames=%d serve_frames=%d dict_frames=%d bad=%d shots=%d\n", TOTAL, serve_frames, dict_frames, bad, shots))
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
