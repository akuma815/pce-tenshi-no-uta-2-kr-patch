-- b11 armchk_v4 실행 여부 추적: PTRL/PTRH/STREAM($C8F2-4) + FLAG 폴링
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b11_armchk]]
local STATE  = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_memo_b11.State]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. [[\probe.tsv]], "w"))
log:write("frame\tPTRL\tPTRH\tSTREAM\tFLAG\tTBANK\tnote\n")
local function rd(a) return memory.read_u8(a, CD) end
for i = 1, 40 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 10 do emu.frameadvance() end
local prev = ""
local function poll(f, note)
  local l = string.format("%02X|%02X|%02X|%02X|%02X",
    rd(0x88F2), rd(0x88F3), rd(0x88F4), rd(0x88F9), rd(0x88FA))
  if l ~= prev or note ~= "" then
    prev = l
    log:write(string.format("%d\t%s\t%s\n", f, l:gsub("|","\t"), note))
    log:flush()
  end
end
poll(0, "state loaded")
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for f = 1, 300 do
  emu.frameadvance()
  poll(f, "")
end
client.screenshot(OUTDIR .. [[\probe_entry.png]])
log:write("done\n"); log:close()
client.exitprogram()
