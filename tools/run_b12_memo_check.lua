-- b11 (armchk_v4) 검증: 메모 목록 스테이트 → 항목 진입 → 대사 한글 확인
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b11_armchk]]
local STATE  = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_memo_b12.State]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')
local log = assert(io.open(OUTDIR .. [[\memo_check_b12.log]], "w"))
local CD = "TurboCD RAM"
local function say(s) log:write(s .. "\n"); log:flush() end
for i = 1, 40 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 10 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\b12_memo_list.png]])
say(string.format("list: FLAG=%02X PRESENT=%02X",
  memory.read_u8(0x88F9, CD), memory.read_u8(0x88FE, CD)))
-- 첫 항목 진입
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for i = 1, 120 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\b12_memo_entry.png]])
say(string.format("entry: FLAG=%02X TBANK=%02X CURL=%02X CURH=%02X",
  memory.read_u8(0x88F9, CD), memory.read_u8(0x88FA, CD),
  memory.read_u8(0x88FB, CD), memory.read_u8(0x88FC, CD)))
for i = 1, 120 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\b12_memo_entry2.png]])
say("done")
log:close()
client.exitprogram()
