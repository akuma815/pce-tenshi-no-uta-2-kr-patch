-- 현재 씬 LBA 표시기 (PCEHawk 전용 — CDL 캡처 파일명 결정용)
-- 사용: PCEHawk(원본 cue + cfg_pcehawk_diag.ini)에서 Lua Console 로 로드.
-- $E009 실행 시 zp 파라미터($FC-$FF)를 읽어 mode-06 96섹터 로드(=씬 로드)의
-- LBA 를 화면 좌상단에 상시 표시하고, 바뀔 때마다 콘솔에 기록한다.
-- CDL 저장 파일명 = translation/cdl/seg_<LBA>_full.cdl
-- (경로 하드코딩 없음 — 표시 전용이라 세션 무관 재사용 가능)

local function dp(a) return memory.read_u8(0x2000 + a, "System Bus") end

-- overlay 씬 디렉터리 전체 (lba -> 섹터수, ziria_module_catalog 실측).
-- ⚠ 96섹터만 씬이 아니다 — 69~94섹터 씬 23개가 더 있다 (2026-08-23 심야
-- 정정: 새 마을 = 578x78. 96 필터 탓에 이전 로드 290 이 stale 표시됐었음).
local SCENES = {
  [290]=96, [386]=96, [482]=96, [578]=78, [674]=96, [770]=96, [866]=96,
  [962]=96, [1058]=83, [1154]=96, [1250]=96, [1346]=96, [1442]=96,
  [1538]=73, [1634]=96, [1730]=92, [1826]=96, [1922]=96, [2018]=82,
  [2114]=75, [2210]=76, [2306]=96, [2402]=96, [2498]=71, [2594]=71,
  [2690]=96, [2786]=69, [2882]=96, [2978]=94, [3074]=96, [3170]=96,
  [3266]=96, [3362]=96, [3458]=96, [3554]=84, [3650]=84, [3746]=96,
  [3842]=96, [3938]=96, [4034]=75, [4130]=96, [4226]=96, [4322]=96,
  [4418]=80, [4514]=82, [4610]=81, [4706]=81, [4802]=90, [4898]=76,
  [4994]=76, [5090]=84, [5186]=96, [5282]=96, [5378]=96,
}

-- 이미 한글화 출하된 씬 — 새 씬이 출하될 때마다 여기 추가.
local COVERED = { [482] = true, [290] = true, [2882] = true, [578] = true }

local scene_lba = nil   -- 마지막 씬(96섹터 mode-06) 로드
local last_any = ""     -- 마지막 로드(참고 표시)
local warn_until = 0    -- 씬 전환 경고 표시 종료 프레임

event.on_bus_exec(function()
  local lba = dp(0xFC) * 0x10000 + dp(0xFD) * 0x100 + dp(0xFE)
  local cnt = dp(0xF8)
  local mode = dp(0xFF)
  last_any = string.format("last read: lba=%d cnt=%d mode=%02X", lba, cnt, mode)
  if mode == 0x06 and SCENES[lba] == cnt then
    if scene_lba ~= lba then
      if scene_lba ~= nil and not COVERED[lba] then
        warn_until = emu.framecount() + 60 * 8   -- 8초 경고 (새 씬만)
      end
      scene_lba = lba
      if COVERED[lba] then
        console.log(string.format(
          "[scene] LBA %d — 이미 한글화 완료된 씬, 캡처 불필요", lba))
      else
        console.log(string.format(
          "[scene] LBA %d NEW ->  CDL: File>New, File>Save As translation\\cdl\\seg_%d_full.cdl",
          lba, lba))
      end
    end
  end
end, 0xE009, "scene lba probe", "System Bus")

console.log("scene LBA 표시기 시작 — 씬 진입 시 콘솔과 화면에 LBA 표시")
console.log("씬마다: CDL File>New -> File>Save As (파일명은 화면 표시). 이후 자동 저장.")
console.log("주의: 씬을 떠나기 '직전' File>Save 한 번 (전환 로드 오염 방지).")
while true do
  if scene_lba then
    if COVERED[scene_lba] then
      gui.text(8, 8, string.format(
        "SCENE LBA: %d — 출하 씬. 처음 오는 지역이면 seg_%d_<지역>.cdl 추가 캡처",
        scene_lba, scene_lba), "cyan")
    else
      gui.text(8, 8, string.format("SCENE LBA: %d NEW — seg_%d_full.cdl 로 캡처",
                                   scene_lba, scene_lba), "lime")
    end
  else
    gui.text(8, 8, "SCENE LBA: (씬 로드 대기)", "yellow")
  end
  gui.text(8, 24, last_any, "gray")
  if emu.framecount() < warn_until then
    gui.text(8, 44, "! 새 씬 감지 — CDL: New -> Save As (새 파일명)", "orange")
    gui.text(8, 60, "  (이전 씬 파일은 떠나기 전 Save 했어야 유효)", "orange")
  end
  emu.frameadvance()
end
