-- Z11 창 수확기 — 사용자가 평소처럼 플레이하는 동안
--   (1) 텍스트가 그려질 때마다 깨끗한 스크린샷을 남기고
--   (2) 그려진 원문 SJIS + 스트림 포인터를 기록한다.
-- 오버레이는 그리지 않는다(보정용 원본 화면이 필요하므로).
-- 코어 PCEHawk + 원본 디스크 + 원본 무헤더 카드.
--
-- ★ 이어붙이기(2026-09-01): 수확은 여러 판에 걸쳐 넓힌다(Z11.3).
--   harvest.tsv 를 덮어쓰지 않고 **이어 쓰며**, shot 번호도 기존 마지막 번호
--   다음부터 시작한다. 그래야 앞 판의 수확(현재 커버리지의 근거)이 안 날아가고
--   스크린샷 파일명도 안 겹친다.

local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe\harvest]]
local TSV    = OUTDIR .. "/harvest.tsv"
local QUIET  = 12     -- 이 프레임 수만큼 새 글자가 없으면 "한 덩어리 끝"으로 본다

local HEADER = "shot\tframe\tnchars\tsjis_hex\tzp52\tzp53\tzp54\tzp55\tmpr4\tframe0\n"

-- 기존 수확을 읽어 마지막 shot 번호를 알아낸다 (없으면 0)
local base_shot, had_rows = 0, false
do
  local f = io.open(TSV, "r")
  if f then
    for line in f:lines() do
      local n = line:match("^(%d+)\t")
      if n then base_shot = math.max(base_shot, tonumber(n)); had_rows = true end
    end
    f:close()
  end
end

local tsv = assert(io.open(TSV, "a"))
if not had_rows then tsv:write(HEADER) end
local log = assert(io.open(OUTDIR .. "/harvest.log", "a"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

local function z(a) return memory.read_u8(0x2000 + a, "System Bus") end

local buf, last_hit, shots, total = {}, -1000, base_shot, 0
-- ★ 스트림 포인터는 **버스트의 첫 글자 시점**에 찍는다 (Z11 §4a.3).
--   QUIET 뒤에 읽으면 엔진이 이미 정리한 값(43/00 또는 00/00)이라 키로 못 쓴다.
local snap0 = nil

event.on_bus_exec(function()
  total = total + 1
  if #buf == 0 then
    snap0 = { z(0x52), z(0x53), z(0x54), z(0x55),
              emu.getregister("MPR-4") or 0, emu.framecount() }
  end
  buf[#buf+1] = string.format("%02X%02X", z(0xF9), z(0xF8))   -- lead, trail
  last_hit = emu.framecount()
end, 0x967E, "Z11 harvest", "System Bus")

say(string.format("수확기 가동 (기존 %d건에 이어 씀). 평소처럼 플레이하세요.", base_shot))
say("  - 대사창/선택지/메뉴/상태창/장비창/전투/메모 를 한 번씩 열어 주세요.")
say("  - Z11.3 은 **중·후반 구간**이 목표입니다 — 새 마을·상점·탑·보스전·")
say("    레벨업·아이템 획득·세이브/로드를 골고루 지나가 주세요.")
say("  - 끝내려면 그냥 EmuHawk 를 닫으세요.")

while true do
  local f = emu.framecount()
  if #buf > 0 and (f - last_hit) >= QUIET then
    shots = shots + 1
    local name = string.format("%s/win_%04d_f%06d.png", OUTDIR, shots, f)
    pcall(client.screenshot, name)
    local s = snap0 or { 0, 0, 0, 0, 0, f }
    tsv:write(string.format("%d\t%d\t%d\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\n",
      shots, f, #buf, table.concat(buf, ""),
      s[1], s[2], s[3], s[4], s[5], s[6]))
    tsv:flush()
    say(string.format("[%d] f%d  %d글자 캡처", shots, f, #buf))
    buf = {}; snap0 = nil
  end
  emu.frameadvance()
end
