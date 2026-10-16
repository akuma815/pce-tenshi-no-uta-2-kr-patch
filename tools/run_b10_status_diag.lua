-- b10 상태창 진단 러너 (TurboNyma, 폴링 전용)
-- 목적: 세이브 로드 → 필드 → 메뉴 → 상태(フェイト) 도달 후 스크린샷.
--   diag 빌드는 iso 0x49DB1(옛 鎧の魔法石 시작, 재패킹 후 "두건")에
--   마커 "타타"를 박아 둠 — 상태창 DX 겹침 글자가 "타타"로 바뀌면
--   stale 참조가 0x49DB1 을 읽는 것으로 확정 (내용 교체 실험).
-- 사용: EmuHawk --config=cfg_b10_play.ini --lua=이파일 ..._b10diag.cue
-- 주의: diag SaveRAM(사용자 세이브 사본) 필요 — 이어하기 경로 전제.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10_status_diag_2026-08-29]]
os.execute('mkdir "' .. OUTDIR .. '" 2>nul')

local log = assert(io.open(OUTDIR .. [[\steps.tsv]], "w"))
local function note(f, s)
  log:write(string.format("%d\t%s\n", f, s)); log:flush()
end
local function shot(f, name)
  client.screenshot(string.format("%s\\%s_f%05d.png", OUTDIR, name, f))
  note(f, "shot " .. name)
end

pcall(function() client.speedmode(800) end)

-- 스케줄: frame -> {버튼셋, 이름} (3프레임 유지)
local presses = {}
local function press(f, btns, name)
  presses[f] = { btns = btns, name = name }
end

-- 1차 런의 입력 프리픽스를 **그대로** 재현한다 (같은 입력+같은 SaveRAM
-- = 결정적 → f3700 필드 도달 재현). 1차 실측: II 백아웃이 타이틀→로드
-- 화면을 넘겼고, f3400/3520 의 I 가 슬롯 1 을 로드했다.
for f = 300, 2280, 120 do
  press(f, { Run = true, I = true }, "mashRunI")
end
for f = 2500, 2900, 80 do
  press(f, { II = true }, "backoutII")
end
press(3000, { Run = true }, "p1_run")
press(3100, { Up = true }, "p1_up1")
press(3140, { Up = true }, "p1_up2")
press(3180, { Up = true }, "p1_up3")
press(3220, { Left = true }, "p1_left1")
press(3260, { Left = true }, "p1_left2")
press(3320, { Right = true }, "p1_right")
press(3400, { I = true }, "p1_loadSlot1")
press(3520, { I = true }, "p1_confirm")
-- 커서 학습 런: 메뉴 열고 Down/Right 를 1프레임씩 눌러 이동 규칙 실측
-- (3프레임 홀드는 고속 모드에서 열기+확정 이중 등록 의심 → 1프레임)
press(4600, { II = true }, "backout1")
press(4680, { II = true }, "backout2")
press(4800, { Run = true }, "openMenu")
press(5000, { Down = true }, "down1")
press(5200, { Down = true }, "down2")
press(5400, { Down = true }, "down3")
press(5600, { Down = true }, "down4")
press(5800, { Down = true }, "down5")
press(6000, { Right = true }, "right1")
press(6200, { Right = true }, "right2")

local active = nil     -- {btns, until_frame}
local TOTAL = 6500

for f = 1, TOTAL do
  local p = presses[f]
  if p then
    -- 부팅 매시(f<4000)는 3프레임 유지, 메뉴 안무는 1프레임 (이중 등록 방지)
    active = { btns = p.btns, till = (f < 4000) and (f + 2) or f }
    note(f, "press " .. p.name)
  end
  if active then
    if f <= active.till then
      pcall(joypad.set, active.btns, 1)
    else
      active = nil
    end
  end
  emu.frameadvance()
  -- 스크린샷: 매시 구간은 240f 마다, 안무 구간은 각 단계 직전/후
  if f == 3090 then shot(f, "loadScreen") end
  if f == 4550 then shot(f, "fieldSettle") end
  if f == 4950 then shot(f, "cur0") end
  if f == 5150 then shot(f, "cur_d1") end
  if f == 5350 then shot(f, "cur_d2") end
  if f == 5550 then shot(f, "cur_d3") end
  if f == 5750 then shot(f, "cur_d4") end
  if f == 5950 then shot(f, "cur_d5") end
  if f == 6150 then shot(f, "cur_r1") end
  if f == 6350 then shot(f, "cur_r2") end
end

note(TOTAL, "done")
log:close()
client.exitprogram()
