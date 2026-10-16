local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b11_armchk]]
local STATE  = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_memo_b12.State]]
local CD = "TurboCD RAM"
local log = assert(io.open(OUTDIR .. [[\probe_b12.tsv]], "w"))
log:write("frame\tPTRL\tPTRH\tSTREAM\tFLAG\tTBANK\tnote\n"); log:flush()
local function rd(a) return memory.read_u8(a, CD) end
for i = 1, 40 do emu.frameadvance() end
local ok, err = pcall(function() savestate.load(STATE) end)
log:write(string.format("0\t--\t--\t--\t--\t--\tstate load %s %s\n",
  tostring(ok), tostring(err))); log:flush()
for i = 1, 10 do emu.frameadvance() end
local prev = ""
local function poll(f, note)
  local l = string.format("%02X|%02X|%02X|%02X|%02X",
    rd(0x88F2), rd(0x88F3), rd(0x88F4), rd(0x88F9), rd(0x88FA))
  if l ~= prev or note ~= "" then
    prev = l
    log:write(string.format("%d\t%s\t%s\n", f, l:gsub("|","\t"), note)); log:flush()
  end
end
poll(0, "loaded")
pcall(joypad.set, { I = true }, 1)
emu.frameadvance()
for f = 1, 300 do emu.frameadvance(); poll(f, "") end
client.screenshot(OUTDIR .. [[\probe_b12_entry.png]])
log:write("done\n"); log:close()
client.exitprogram()
