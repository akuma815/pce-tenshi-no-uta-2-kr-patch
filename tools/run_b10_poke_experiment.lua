-- diag_menu.State 기반 포크 실험 (TurboNyma)
-- 가설: 상태창 템플릿의 민(0x8C7E) 트레일 0x7E 가 ~(간격) 스캐너에 오인돼
--       두 라벨 X 가 무너진다.
-- E1 = 무포크 기준, E2 = 민→이(0x889F), E3 = 민→0x8C40(트레일만 교체).
-- 각 실험: 스테이트 로드 → 포크 → I(상태 확정) → I(フェイト) → 스크린샷.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b10_status_diag_2026-08-29]]
local STATE = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\BizHawk-master\output\PC Engine\State\diag_menu.State]]

local log = assert(io.open(OUTDIR .. [[\poke_experiment.log]], "w"))
local function say(s) log:write(s .. "\n"); log:flush() end

local BUS = "System Bus (21 bit)"
local MIN_ADDR = 0x109D7B          -- 템플릿 내 '민' (8C 7E) 물리 주소

local function rd(a) return memory.read_u8(a, BUS) end

local function try_write(a, v)
  memory.write_u8(a, v, BUS)
  return rd(a) == v
end

local function press(btn)
  pcall(joypad.set, { [btn] = true }, 1)
  emu.frameadvance()
  for i = 1, 39 do emu.frameadvance() end
end

-- RAM 템플릿 민첩 줄: 좌(109D78) \r(7A) 민(7B) 첩(7D) 　(7F) ~(81) ~×12(82-8D) 두(8E)
local L = 0x109D78
local function bytes_at(t)
  local m = {}
  for i, v in ipairs(t) do m[L + i - 1] = v end
  return m
end
local experiments = {
  { name = "E4_cheob_to_neung", poke = { [0x109D7D] = 0x8C, [0x109D7E] = 0xB7 } },
  { name = "E5_space_to_tildes", poke = { [0x109D7F] = 0x7E, [0x109D80] = 0x7E } },
  { name = "E7_restore_orig_head", poke = bytes_at({ 0x8D, 0xB6, 0x0D, 0x91, 0x66, 0x91, 0x81, 0x3C, 0x81, 0x40 }) },
}

for i = 1, 40 do emu.frameadvance() end

for _, ex in ipairs(experiments) do
  savestate.load(STATE)
  for i = 1, 10 do emu.frameadvance() end
  say(ex.name .. ": state loaded, template bytes = " ..
      string.format("%02X %02X", rd(MIN_ADDR), rd(MIN_ADDR + 1)))
  local ok = true
  if ex.poke then
    for a, v in pairs(ex.poke) do
      if not try_write(a, v) then ok = false end
    end
    say(ex.name .. ": poke " .. (ok and "OK" or "FAILED(read-back mismatch)") ..
        ", now = " .. string.format("%02X %02X", rd(MIN_ADDR), rd(MIN_ADDR + 1)))
  end
  press("I")                       -- 상태 확정 (커서 = 状態)
  for i = 1, 20 do emu.frameadvance() end
  press("I")                       -- フェイト 선택
  for i = 1, 140 do emu.frameadvance() end
  client.screenshot(OUTDIR .. "\\poke_" .. ex.name .. ".png")
  say(ex.name .. ": shot")
end

say("done")
log:close()
client.exitprogram()
