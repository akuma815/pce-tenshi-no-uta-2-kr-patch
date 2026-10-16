-- TurboNyma 호환 폴링 추적기 (이벤트 콜백 불사용)
local out = assert(io.open([[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\f215ea6b-5249-4850-a49a-7d9d5d50dea5\scratchpad\bios_retest\nyma_poll.tsv]], "w"))
out:write("frame\tstate7E\tsig7E\tmagic6D\tFLAG\tPRESENT\n") out:flush()
local SCD = "Super System Card RAM"
local CD = "TurboCD RAM"
local POOL7E = "25663023"
local ORG7E  = "07070707"
local prev = ""
local function sig(dom, off)
  return string.format("%02x%02x%02x%02x",
    memory.read_u8(off,dom), memory.read_u8(off+1,dom),
    memory.read_u8(off+2,dom), memory.read_u8(off+3,dom))
end
for f=1,999999 do
  emu.frameadvance()
  if f % 10 == 0 then
    local s7e = sig(SCD, 0x2C000)
    local m6d = sig(SCD, 0x0A000)
    local flag = memory.read_u8(0x0F9B, CD)
    local pres = memory.read_u8(0x88FE, CD)
    local st = "OTHER"
    if s7e == POOL7E then st = "POOL"
    elseif s7e == ORG7E then st = "ORIG482" end
    local line = st.."|"..s7e.."|"..m6d.."|"..flag.."|"..pres
    if line ~= prev or f % 1800 == 0 then
      prev = line
      out:write(string.format("%d\t%s\t%s\t%s\t%02X\t%02X\n", f, st, s7e, m6d, flag, pres))
      out:flush()
    end
  end
end