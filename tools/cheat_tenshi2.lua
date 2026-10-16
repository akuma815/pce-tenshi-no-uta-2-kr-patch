-- 천사의 시 II 테스트용 치트 (TurboNyma, BizHawk Lua). 2026-10-10 실측 주소 (Main Memory = 워크 RAM $2000-$3FFF → 0x0000-0x1FFF).
--   필드 파티 배열(4칸, 1바이트씩, lo/hi 분리): 레벨-1 0x1D63 / EXP 0x1D67·0x1D6B·0x1D6F(3바이트) / HP 0x1D7F·hi 0x1D83 / 최대HP 0x1D87·0x1D8B
--                                           MP 0x1D8F·0x1D93 / 최대MP 0x1D97·0x1D9B
--   전투 블록(12칸 = 파티 4 + 적 8): HP 0x121C·hi 0x1228 / 최대HP 0x1234·0x1240 / MP 0x124C·0x1258 / 최대MP 0x1264·0x1270
--   전투 피해는 전투 블록에만 쌓이고 전투가 끝날 때 필드 배열로 돌아간다 → 무적은 두 곳 모두 매 프레임 최대값으로.
--   최고 레벨: EXP 를 16,000,000 으로 올려 두면 **다음 전투가 끝날 때** 게임이 스스로 Lv99 까지 연속 레벨업(스탯 성장 포함, 실측 PASS).
--   (2026-10-11) 전투 즉시 종료: 전투 중(0x0005 = 0x00, 필드는 0x80)에 적 칸(전투 블록 4~11)의 HP 가 1 보다 크면 1 로 → 첫 공격에 쓰러짐(경험치·돈 정상).
--   랜덤 인카운터 자체를 끄는 주소는 못 찾음(걸음마다 공용 난수 $22D4/D5 로 판정). 이벤트 전투도 즉시 끝나니 필요하면 CHEAT_NO_INSTANT=1 로 끈다.
local INVINCIBLE = true
local INFINITE_MP = true
local MAX_LEVEL = (os.getenv("CHEAT_NO_LEVEL") == nil)   -- 최고 레벨을 원치 않으면 false 로
local EXP_TARGET = 16000000
local INSTANT_WIN = (os.getenv("CHEAT_NO_INSTANT") == nil)
local D = "Main Memory"
local function r(a) return memory.read_u8(a, D) end
local function w(a, v) memory.write_u8(a, v, D) end
local function copy16(dlo, dhi, slo, shi) w(dlo, r(slo)); w(dhi, r(shi)) end
local function apply()
  if INSTANT_WIN and r(0x0005) == 0 then                 -- 전투 중: 적 8칸(전투 블록 4~11) HP 를 1 로
    for e = 4, 11 do
      if (r(0x1234 + e) + r(0x1240 + e)) > 0 and (r(0x121C + e) + r(0x1228 + e) * 256) > 1 then w(0x121C + e, 1); w(0x1228 + e, 0) end
    end
  end
  for i = 0, 3 do
    local present = (r(0x1D87 + i) + r(0x1D8B + i)) > 0
    if present then
      if INVINCIBLE then copy16(0x1D7F + i, 0x1D83 + i, 0x1D87 + i, 0x1D8B + i) end
      if INFINITE_MP then copy16(0x1D8F + i, 0x1D93 + i, 0x1D97 + i, 0x1D9B + i) end
      if MAX_LEVEL then
        local exp = r(0x1D67 + i) + r(0x1D6B + i) * 256 + r(0x1D6F + i) * 65536
        if exp < EXP_TARGET then w(0x1D67 + i, EXP_TARGET % 256); w(0x1D6B + i, (EXP_TARGET // 256) % 256); w(0x1D6F + i, EXP_TARGET // 65536) end
      end
    end
    if (r(0x1234 + i) + r(0x1240 + i)) > 0 then           -- 전투 블록이 채워져 있을 때만
      if INVINCIBLE then copy16(0x121C + i, 0x1228 + i, 0x1234 + i, 0x1240 + i) end
      if INFINITE_MP then copy16(0x124C + i, 0x1258 + i, 0x1264 + i, 0x1270 + i) end
    end
  end
end
event.onframeend(apply, "tenshi2_cheat")
console.log("천사의 시 II 치트 ON: 무적=" .. tostring(INVINCIBLE) .. " MP무한=" .. tostring(INFINITE_MP) .. " 최고레벨(다음 전투 후)=" .. tostring(MAX_LEVEL) .. " 전투즉시종료=" .. tostring(INSTANT_WIN))
