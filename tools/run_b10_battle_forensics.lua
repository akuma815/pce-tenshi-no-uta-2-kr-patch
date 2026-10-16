-- diag_battle1.State 로드 → RAM 포렌식 덤프 (TurboNyma)
-- 목적: 상태창 렌더 시점의 실제 메모리에서 두 라벨 앞 바이트를 확인.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10_status_diag_2026-08-29]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_battle1.State]]

local log = assert(io.open(OUTDIR .. [[\forensics_battle.log]], "w"))
local function say(s) log:write(s .. "\n"); log:flush() end

for i = 1, 40 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 5 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\state_battle1.png]])
say("state loaded, screenshot taken")

local BUS = "System Bus (21 bit)"

local function dump(path, base, len)
  local f = assert(io.open(path, "wb"))
  local CHUNK = 4096
  local pos = 0
  while pos < len do
    local n = math.min(CHUNK, len - pos)
    local arr = memory.read_bytes_as_array(base + pos, n, BUS)
    local t = {}
    for i = 1, n do t[i] = string.char(arr[i]) end
    f:write(table.concat(t))
    pos = pos + n
  end
  f:close()
  say(string.format("dumped %s: base %X len %X", path, base, len))
end

-- CD RAM 뱅크 $68-$87 (256KB)
dump(OUTDIR .. [[\cdram_battle.bin]], 0x68 * 0x2000, 0x20 * 0x2000)
-- 메인 RAM 뱅크 $F8 (8KB)
dump(OUTDIR .. [[\mainram_battle.bin]], 0xF8 * 0x2000, 0x2000)

say("done")
log:close()
client.exitprogram()
