-- PCEHawk: CD-DA/BIOS 벡터 호출 실측 — BGM 재생이 트랙번호 기반인지 MSF 기반인지 판정.
-- $E00C..$E02D 벡터 전부 exec 훅 ($E009 CD_READ 는 제외 — 소음).
-- 사용: PCEHawk + 원본 JAP.cue. 타이틀→게임시작→필드→전투 등 BGM 전환 2~3회면 충분.
-- 출력: translation/b4_debug_2026-08-23/cdda_calls.tsv

local OUT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b4_debug_2026-08-23\cdda_calls.tsv]]
local log = assert(io.open(OUT, "w"))
log:write("frame\tvector\tA\tX\tY\tzpF8..FF\tcaller\n")
log:flush()

local function dp(a) return memory.read_u8(0x2000 + a, "System Bus") end
local function bus(a) return memory.read_u8(a, "System Bus") end

local ncalls = 0
local last = ""

local function make_hook(vec)
  return function()
    local s = emu.getregister("S")
    local caller = bus(0x2100 + ((s + 2) % 256)) * 256 + bus(0x2100 + ((s + 1) % 256)) - 2
    local zp = {}
    for i = 0xF8, 0xFF do zp[#zp + 1] = string.format("%02X", dp(i)) end
    ncalls = ncalls + 1
    last = string.format("%04X @%04X", vec, caller)
    log:write(string.format("%d\t%04X\t%02X\t%02X\t%02X\t%s\t%04X\n",
      emu.framecount(), vec,
      emu.getregister("A"), emu.getregister("X"), emu.getregister("Y"),
      table.concat(zp, " "), caller))
    log:flush()
  end
end

for vec = 0xE00C, 0xE02D, 3 do
  event.on_bus_exec(make_hook(vec), vec, string.format("cdda %04X", vec), "System Bus")
end

console.log("CD-DA 벡터 추적 시작 — BGM 전환을 몇 번 일으켜 주세요")
while true do
  emu.frameadvance()
  gui.text(8, 30, string.format("cdda calls %d  last %s", ncalls, last), "yellow")
end
