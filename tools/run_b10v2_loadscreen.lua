-- B9 full-build smoke (TurboNyma, 폴링 전용)
-- 부팅→새 게임→첫 대사 자동 진행 + FLAG/TBANK 폴링 + 확장 뱅크 물리 스윕.
-- PASS: FLAG=01 & TBANK ∈ EXT($20-$3F,$44-$4F) 관측 + 첫 대사 한글 스크린샷
--       + sweep 에서 사용 뱅크 전부 카드 바이트 가시 (Arcade 섀도우 = $40-$43).
-- 주의: SaveRAM 없는 상태로 실행 (세이브가 있으면 '이어하기'로 빠짐).
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10v2_loadscreen_2026-08-29]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')

local log = assert(io.open(OUTDIR .. [[\poll.tsv]], "w"))
log:write("frame\tFLAG\tTBANK\tCURL\tCURH\tPRESENT\tnote\n")
log:flush()

local CD = "TurboCD RAM"
local BUS21 = "System Bus (21 bit)"
local F_FLAG, F_TBANK, F_CURL, F_CURH, F_PRESENT =
  0x88F9, 0x88FA, 0x88FB, 0x88FC, 0x88FE

local st = assert(io.open(OUTDIR .. [[\status.txt]], "w"))
local names = memory.getmemorydomainlist()
local doms = {}
for i = 0, #names do if names[i] then doms[#doms + 1] = names[i] end end
st:write("domains: " .. table.concat(doms, " | ") .. "\n")
st:flush()

local function ext_ok(tb)
  return (tb >= 0x20 and tb <= 0x3F) or (tb >= 0x44 and tb <= 0x4F)
end

pcall(function() client.speedmode(800) end)

local prev = ""
local pocshots, poc_frames, last_shot = 0, 0, -999
local swept = false
local TOTAL = 4000

for f = 1, TOTAL do
  local pulse = f > 300 and f % 120 < 3
  if pulse then
    pcall(joypad.set, { Run = true }, 1)
  end
  emu.frameadvance()
  if f == 2400 and not swept then
    swept = true
    for b = 0x20, 0x5F do
      st:write(string.format("bank%02X: %02X%02X\n", b,
        memory.read_u8(b * 0x2000, BUS21),
        memory.read_u8(b * 0x2000 + 1, BUS21)))
    end
    st:flush()
  end
  local flag = memory.read_u8(F_FLAG, CD)
  local tb = memory.read_u8(F_TBANK, CD)
  local cl = memory.read_u8(F_CURL, CD)
  local ch = memory.read_u8(F_CURH, CD)
  local pr = memory.read_u8(F_PRESENT, CD)
  local note = ""
  if flag == 1 and ext_ok(tb) then
    poc_frames = poc_frames + 1
    if pocshots < 12 and f - last_shot >= 60 then
      pocshots = pocshots + 1
      last_shot = f
      client.screenshot(string.format("%s\\pocserve_%02d_f%05d.png",
        OUTDIR, pocshots, f))
      note = "POC_SERVE_SHOT"
    else
      note = "POC_SERVE"
    end
  end
  local line = string.format("%02X|%02X|%02X", flag, tb, pr)
  if line ~= prev or note ~= "" then
    prev = line
    log:write(string.format("%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n",
      f, flag, tb, cl, ch, pr, note))
    log:flush()
  end
  if f % 120 == 118 then
    client.screenshot(string.format("%s\\walk_f%05d.png", OUTDIR, f))
  end
end

st:write(string.format("done frames=%d poc_frames=%d pocshots=%d\n",
  TOTAL, poc_frames, pocshots))
st:close()
log:close()
client.exitprogram()
