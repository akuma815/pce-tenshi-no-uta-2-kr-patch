-- b4 진단 v2: 모든 CD read($E009) + 훅 arm/nul + 상태 (검증된 read_dp 방식)
local out = assert(io.open([[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\btrack_b4_load_trace.tsv]], "w"))
out:write("frame\tevent\tlba\tcount\tmode\tzpF9_FA_FB\tFLAG\tCUR\tTBANK\n")
out:flush()
local function dp(a) return memory.read_u8(0x2000 + a, "System Bus") end
local function bus(a) return memory.read_u8(a, "System Bus") end
event.on_bus_exec(function()
  local lba = dp(0xFC)*0x10000 + dp(0xFD)*0x100 + dp(0xFE)
  out:write(string.format("%d\tCD\t%d\t%d\t%02X\t%02X%02X%02X\t%02X\t%02X%02X\t%02X\n",
    emu.framecount(), lba, dp(0xF8), dp(0xFF), dp(0xF9), dp(0xFA), dp(0xFB),
    bus(0x4F9B), bus(0x4FA0), bus(0x4F9F), bus(0x4F9C)))
  out:flush()
end, 0xE009, "b4 cd", "System Bus")
event.on_bus_exec(function()
  out:write(string.format("%d\tHOOK737\t\t\t\t\t%02X\t%02X%02X\t%02X\n",
    emu.framecount(), bus(0x4F9B), bus(0x4FA0), bus(0x4F9F), bus(0x4F9C)))
  out:flush()
end, 0xC737, "b4 c737", "System Bus")
event.on_bus_exec(function()
  out:write(string.format("%d\tARM\t\t\t\t\t%02X\t%02X%02X\t%02X\n",
    emu.framecount(), bus(0x4F9B), bus(0x4FA0), bus(0x4F9F), bus(0x4F9C)))
  out:flush()
end, 0x4F6B, "b4 arm", "System Bus")
event.on_bus_exec(function()
  out:write(string.format("%d\tNUL\t\t\t\t\t%02X\t%02X%02X\t\n",
    emu.framecount(), bus(0x4F9B), bus(0x4FA0), bus(0x4F9F)))
  out:flush()
end, 0x4F49, "b4 nul", "System Bus")
console.log("b4 trace v2 armed")
while true do emu.frameadvance() end
