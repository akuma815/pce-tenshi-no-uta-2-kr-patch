-- B9-PoC 확장 뱅크($20) read 런타임 검증 (TurboNyma, 폴링 전용 — 콜백 불사용)
-- 부팅→타이틀→새 게임→첫 대사를 펄스 입력으로 자동 진행하면서
-- FLAG($C8F9)/TBANK($C8FA)를 TurboCD RAM 도메인으로 폴링한다.
-- PASS 신호: FLAG=01 & TBANK=20 구간 관측(poll.tsv POC_SERVE 행)
--            + pocserve/walk 스크린샷의 첫 대사 한글이 b8.3 과 동일.
-- 사용: EmuHawk --config=cfg_b9poc_play.ini --lua=이파일 b9poc.cue
-- 주의: SaveRAM(..._b9poc.SaveRAM)이 없는 상태로 실행할 것 — 세이브가 있으면
--       펄스가 '이어하기'를 골라 첫 대사에 못 간다.

local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b9poc768_runtime_2026-08-28]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')

local log = assert(io.open(OUTDIR .. [[\poll.tsv]], "w"))
log:write("frame\tFLAG\tTBANK\tCURL\tCURH\tPRESENT\tnote\n")
log:flush()

local CD = "TurboCD RAM" -- banks $80-$87. FLAG 등은 bank $84 = off 0x8000+
local F_FLAG, F_TBANK, F_CURL, F_CURH, F_PRESENT =
  0x88F9, 0x88FA, 0x88FB, 0x88FC, 0x88FE

-- 도메인/버튼 이름 채증 (이름 불일치 진단용)
local st = assert(io.open(OUTDIR .. [[\status.txt]], "w"))
local names = memory.getmemorydomainlist()
local doms = {}
for i = 0, #names do if names[i] then doms[#doms + 1] = names[i] end end
st:write("domains: " .. table.concat(doms, " | ") .. "\n")
local keys = {}
for k, _ in pairs(joypad.get(1)) do keys[#keys + 1] = k end
table.sort(keys)
st:write("pad1: " .. table.concat(keys, ",") .. "\n")
st:flush()

pcall(function() client.speedmode(800) end)

local prev = ""
local pocshots, poc_frames, last_shot = 0, 0, -999
local TOTAL = 24000

for f = 1, TOTAL do
  local pulse = f > 300 and f % 120 < 3
  if pulse then
    pcall(joypad.set, { Run = true, I = true, II = true }, 1)
    pcall(joypad.set, { Run = true, B1 = true, B2 = true }, 1)
  end
  emu.frameadvance()
  local flag = memory.read_u8(F_FLAG, CD)
  local tb = memory.read_u8(F_TBANK, CD)
  local cl = memory.read_u8(F_CURL, CD)
  local ch = memory.read_u8(F_CURH, CD)
  local pr = memory.read_u8(F_PRESENT, CD)
  local note = ""
  if flag == 1 and tb == 0x20 then
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
