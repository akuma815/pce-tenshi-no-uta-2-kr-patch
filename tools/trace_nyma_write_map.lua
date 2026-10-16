-- 원본 게임 쓰기 활동 지도: 로드 없이 변하는 샘플 지점 검출 (TurboNyma 폴링)
local out = assert(io.open([[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\f215ea6b-5249-4850-a49a-7d9d5d50dea5\scratchpad\bios_retest\write_map.tsv]], "w"))
out:write("frame\tbank\toff\told\tnew\n") out:flush()
local SCD = "Super System Card RAM"
local prev = {}
local last_write = {}
for f=1,999999 do
  emu.frameadvance()
  if f % 10 == 0 then
    for b=0,23 do
      for p=0,7 do
        local off = b*0x2000 + p*0x400
        local v = memory.read_u32_le(off, SCD)
        local k = b*8+p
        if prev[k] ~= nil and prev[k] ~= v then
          out:write(string.format("%d\t%02X\t%04X\t%08x\t%08x\n",
            f, 0x68+b, p*0x400, prev[k], v))
        end
        prev[k] = v
      end
    end
    out:flush()
  end
end