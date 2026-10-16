local out = assert(io.open([[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\f215ea6b-5249-4850-a49a-7d9d5d50dea5\scratchpad\bios_retest\e009_callers2.tsv]], "w"))
out:write("frame\tlba\tcount\tmode\tcaller\tmprs\n") out:flush()
local function dp(a) return memory.read_u8(0x2000 + a, "System Bus") end
local function bus(a) return memory.read_u8(a, "System Bus") end
event.on_bus_exec(function()
  local s = emu.getregister("S")
  local caller = bus(0x2100 + ((s+2)%256))*256 + bus(0x2100 + ((s+1)%256)) - 2
  local m = string.format("%02X%02X%02X%02X%02X",
    emu.getregister("MPR-2"), emu.getregister("MPR-3"), emu.getregister("MPR-4"),
    emu.getregister("MPR-5"), emu.getregister("MPR-6"))
  out:write(string.format("%d\t%d\t%d\t%02X\t%04X\t%s\n",
    emu.framecount(), dp(0xFC)*0x10000+dp(0xFD)*0x100+dp(0xFE), dp(0xF8), dp(0xFF), caller, m))
  out:flush()
end, 0xE009, "e009 callers", "System Bus")
console.log("E009 caller trace armed — 플레이하세요")
while true do emu.frameadvance() end