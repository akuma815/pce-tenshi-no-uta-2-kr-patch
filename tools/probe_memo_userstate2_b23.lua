local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b23_runtime\userstate]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b23.TurboNyma.QuickSave1.State]]
local B21 = "System Bus (21 bit)"
local log = assert(io.open(OUTDIR .. "/probe2.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function r21(a) return memory.read_u8(a, B21) end
local function hex(a, n) local t = {} for k = 0, n - 1 do t[#t+1] = string.format("%02X", r21(a + k)) end return table.concat(t, " ") end
for i = 1, 30 do emu.frameadvance() end
say("load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 5 do emu.frameadvance() end
local ENG = 0x84 * 0x2000
say("scratch $C8C8-$C8FF: " .. hex(ENG + 0x8C8, 0x38))
local ibank, ibase = r21(ENG + 0x8CC), r21(ENG + 0x8CD)
say(string.format("IBANK=%02X IBASE=%02X", ibank, ibase))
local ipage = ibank * 0x2000 + (ibase - 0xA0) * 0x100
say("index page (256B): " .. hex(ipage, 256))
local lo, hi = r21(ipage + 2 + 0x17 * 2), r21(ipage + 3 + 0x17 * 2)
say(string.format("kb17 subtable ptr = %02X%02X", hi, lo))
local sub = ibank * 0x2000 + ((hi * 256 + lo) - 0xA000)
say("kb17 records: " .. hex(sub, 7 * 12))
say("scene $7F:$0040..: " .. hex(0x7F * 0x2000 + 0x40, 0x60))
-- 결정 후 첫 프레임들에서 2D80 / 포인터 세밀 추적은 probe.log 에 있음
log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
