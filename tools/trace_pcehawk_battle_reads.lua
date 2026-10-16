-- PCEHawk 전용: 전투 중 CD read 전수 로그 + 풀 구간(LBA 5480..5493) 히트 감지
-- 목적: 필드 인카운터 전투가 풀 디스크 섹터를 읽는지 확정 (원본 게임 + 원본 카드로 실행)
-- 사용: PCEHawk 코어 + 원본 JAP.cue + 이 스크립트. 필드 전투 2~5회 (맵 이동 포함).
-- 화면 좌상단에 read 카운트, 풀 구간 히트 시 빨간 HIT 표시 + 로그 표식.

local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\v9_probe]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')
local out = assert(io.open(OUTDIR .. [[\battle_reads.tsv]], "w"))
out:write("frame\tlba\tcount\tmode\tcaller\tmprs\tpoolhit\n") out:flush()

local POOL_LO, POOL_HI = 5480, 5493   -- ISO(Track02) 상대 LBA
local nreads, nhits, lasthit = 0, 0, ""

local function dp(a) return memory.read_u8(0x2000 + a, "System Bus") end
local function bus(a) return memory.read_u8(a, "System Bus") end

event.on_bus_exec(function()
  local s = emu.getregister("S")
  local caller = bus(0x2100 + ((s + 2) % 256)) * 256 + bus(0x2100 + ((s + 1) % 256)) - 2
  local m = string.format("%02X%02X%02X%02X%02X",
    emu.getregister("MPR-2"), emu.getregister("MPR-3"), emu.getregister("MPR-4"),
    emu.getregister("MPR-5"), emu.getregister("MPR-6"))
  local lba = dp(0xFC) * 0x10000 + dp(0xFD) * 0x100 + dp(0xFE)
  local cnt = dp(0xF8)
  local hit = ""
  if lba <= POOL_HI and lba + cnt > POOL_LO then
    hit = "POOLHIT"
    nhits = nhits + 1
    lasthit = string.format("lba %d+%d caller %04X f%d", lba, cnt, caller, emu.framecount())
  end
  nreads = nreads + 1
  out:write(string.format("%d\t%d\t%d\t%02X\t%04X\t%s\t%s\n",
    emu.framecount(), lba, cnt, dp(0xFF), caller, m, hit))
  out:flush()
end, 0xE009, "e009 battle reads", "System Bus")

console.log("battle read trace armed — 필드 전투를 플레이하세요")
while true do
  emu.frameadvance()
  gui.text(4, 4, string.format("reads %d", nreads), "white")
  if nhits > 0 then
    gui.text(4, 20, string.format("POOL HIT x%d  %s", nhits, lasthit), "red")
  end
end
