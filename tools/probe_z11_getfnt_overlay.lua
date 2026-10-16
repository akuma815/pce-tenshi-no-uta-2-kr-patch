-- Z11 P1/P3/P4/P5 프로브 — EX_GETFNT 훅 실동작 + gui 한글 렌더 + 프레임 비용
-- 코어: PCEHawk 전용 (event.on_bus_exec 는 PCEHawk 에서만 발화)
-- 카드: probes/SystemCard3_original_noheader.pce (원본 무헤더)
-- 디스크: Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue (원본 무수정)

local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local TAG    = "TAGX"          -- 실행 래퍼가 치환
local STATE  = [[STATEX]]      -- 실행 래퍼가 치환 ("" = 스테이트 없이 진행)
local BUDGET = 900             -- 총 프레임

local tsv = assert(io.open(OUTDIR .. "/p1_" .. TAG .. ".tsv", "w"))
local log = assert(io.open(OUTDIR .. "/p1_" .. TAG .. ".log", "w"))
tsv:write("frame\tsjis\tmode\tsrc_ptr\tdest\thit\n")
local function say(s) log:write(s .. "\n"); log:flush(); console.log(s) end

local function zp(a) return memory.read_u8(0x2000 + a, "System Bus") end

local pending, n_entry, n_copy = nil, 0, 0
local seen = {}          -- 고유 SJIS 집계
local last_frame_chars = 0

local function on_entry()
  n_entry = n_entry + 1
  pending = { f = emu.framecount(), lead = zp(0xF8), trail = zp(0xF9), mode = zp(0xFF) }
end

local function on_copy()
  n_copy = n_copy + 1
  local src  = zp(0xEC) + zp(0xED) * 0x100
  local dest = zp(0xFA) + zp(0xFB) * 0x100
  local p = pending or { f = emu.framecount(), lead = 0, trail = 0, mode = zp(0xFF) }
  local sjis = string.format("%02X%02X", p.lead, p.trail)
  seen[sjis] = (seen[sjis] or 0) + 1
  last_frame_chars = last_frame_chars + 1
  tsv:write(string.format("%d\t%s\t%02X\t%04X\t%04X\t%d\n", p.f, sjis, p.mode, src, dest, n_copy))
  tsv:flush()
  if n_copy <= 40 then
    say(string.format("GETFNT #%d f%d sjis=%s mode=%02X src=%04X dest=%04X",
        n_copy, p.f, sjis, p.mode, src, dest))
  end
  pending = nil
end

event.on_bus_exec(on_entry, 0xF124, "Z11 entry", "System Bus")
event.on_bus_exec(on_copy,  0xF1B9, "Z11 copy",  "System Bus")

-- ---------- P3: gui 한글 렌더 ----------
local KO = "한글 자막 테스트 — 가나다라 힣"
local function draw_p3()
  -- (a) 불투명 박스 = 원본 창 덮어쓰기 실증
  pcall(gui.drawRectangle, 8, 150, 240, 44, 0xFF000000, 0xFF000000)
  -- (b) gui.text (기본 폰트)
  pcall(gui.text, 8, 8, "gui.text: " .. KO)
  -- (c) gui.drawText 기본 폰트
  pcall(gui.drawText, 12, 154, "drawText: " .. KO, 0xFFFFFFFF, 0xFF000000, 12)
  -- (d) gui.drawText + 한국어 폰트 지정
  pcall(gui.drawText, 12, 172, "Malgun: " .. KO, 0xFF00FF00, 0xFF000000, 12, "Malgun Gothic")
end

-- ---------- 실행 ----------
pcall(client.speedmode, 400)   -- 일회용 config 사본에서만 실행할 것 (P4 실측용)
say(string.format("start core=%s rom=%s", tostring(emu.getsystemid()), tostring(gameinfo.getromname())))
for i = 1, 30 do draw_p3(); emu.frameadvance() end

if STATE ~= "" then
  local ok, err = pcall(function() savestate.load(STATE) end)
  say("state load: " .. tostring(ok) .. " " .. tostring(err))
else
  say("state: (none) — 부팅 상태에서 진행")
end

local t0 = os.clock()
for f = 1, BUDGET do
  -- 대사 진행: I 펄스
  if f % 90 < 3 then pcall(joypad.set, { I = true, Run = (f < 200) }, 1) end
  draw_p3()
  emu.frameadvance()
  if f == 5 or f == 60 or f == 300 or f == 600 or f == BUDGET then
    client.screenshot(string.format("%s/p3_%s_f%04d.png", OUTDIR, TAG, f))
    say(string.format("f%d shot  entry=%d copy=%d", f, n_entry, n_copy))
  end
end
local wall = os.clock() - t0

-- ---------- 집계 ----------
local uniq = 0
for _ in pairs(seen) do uniq = uniq + 1 end
say(string.format("RESULT entry=%d copy=%d uniq_sjis=%d frames=%d wall=%.1fs fps=%.1f",
    n_entry, n_copy, uniq, BUDGET, wall, BUDGET / math.max(wall, 0.001)))
say("P1 = " .. (n_copy > 0 and "HIT" or "MISS"))

local st = assert(io.open(OUTDIR .. "/p1_" .. TAG .. "_status.txt", "w"))
st:write(string.format("tag=%s\nstate=%s\nentry=%d\ncopy=%d\nuniq_sjis=%d\nframes=%d\nwall_s=%.2f\nfps=%.1f\nverdict=%s\n",
    TAG, STATE, n_entry, n_copy, uniq, BUDGET, wall, BUDGET / math.max(wall, 0.001),
    n_copy > 0 and "P1_HIT" or "P1_MISS"))
st:close()
tsv:close(); log:close()
client.exitprogram()
