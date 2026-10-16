-- b9 v2 무장 실패 진단 (TurboNyma 폴링)
-- 관측: SCRATCH+0..7 (IBANK/IBASE 자리), 물리 버스로 카드 확장 뱅크 가시성
--   (0x84000 = 482 인덱스 매직 42 B4 기대, 0x40000 = 텍스트 풀 81 44 기대,
--    0x3FA00 = armchk_v3 머리 DA 5A 기대), zp $53/$4B/$4C, $2E69/$22D0.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b9_diag_2026-08-28]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')
local log = assert(io.open(OUTDIR .. [[\diag.tsv]], "w"))
log:write("frame\tPRES\tFLAG\tscratch_c8c8_8B\tphys84000_2B\tphys40000_2B\tphys3FA00_2B\tzp53\tzp4B4C\tm2E69\tm22D0\n")
log:flush()

local CD = "TurboCD RAM"
local BUS21 = "System Bus (21 bit)"
local SB = "System Bus"

local function hexs(dom, off, n)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.format("%02X", memory.read_u8(off + i, dom)) end
  return table.concat(t)
end

pcall(function() client.speedmode(800) end)
local prev = ""
for f = 1, 10000 do
  local pulse = f > 300 and f % 120 < 3
  if pulse then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  emu.frameadvance()
  if f % 30 == 0 then
    local line = string.format("%02X\t%02X\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s",
      memory.read_u8(0x88FE, CD), memory.read_u8(0x88F9, CD),
      hexs(CD, 0x88C8, 8),
      hexs(BUS21, 0x84000, 2), hexs(BUS21, 0x40000, 2), hexs(BUS21, 0x3FA00, 2),
      hexs(SB, 0x2053, 1), hexs(SB, 0x204B, 2),
      hexs(SB, 0x2E69, 1), hexs(SB, 0x22D0, 1))
    if line ~= prev then
      prev = line
      log:write(f .. "\t" .. line .. "\n")
      log:flush()
    end
  end
  if f % 600 == 598 then
    client.screenshot(string.format("%s\\diag_f%05d.png", OUTDIR, f))
  end
end
log:close()
client.exitprogram()
