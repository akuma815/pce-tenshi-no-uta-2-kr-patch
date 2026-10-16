-- b17 타이틀 확인: 부팅 후 2700프레임에 스크린샷 (TurboNyma, b17 카드). 입력 없음.
local OUTDIR = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)\translation\b17_runtime]]
for f = 1, 2700 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\title_b17.png]])
for f = 1, 60 do emu.frameadvance() end
client.screenshot(OUTDIR .. [[\title_b17_b.png]])
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
