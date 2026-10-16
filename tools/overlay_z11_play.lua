-- Z11 오버레이 — 플레이 모드 진입점.
-- 사람이 켜 놓고 그냥 플레이한다. 세이브스테이트 로드도, 자동 입력도, 종료도 없다.
-- 로직은 overlay_z11_final.lua 하나가 소유한다 (사본을 만들면 반드시 어긋난다).
-- 로그 = translation/z11_probe/z11_play.log
--   · `match=no` / `MISS key=...` 줄이 곧 잔존 일문이다. 0 이어야 Z11.4 판정 PASS.
Z11_PLAY = true
dofile([[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\tools\overlay_z11_final.lua]])
