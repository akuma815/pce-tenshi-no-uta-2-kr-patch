-- Z11 진단 — 대사창이 BAT 어디에 있는가 (내 영역 가정의 직접 검증)
--  방법: 대사 표시 중 BAT 전체를 타일번호로 덤프하고, 행별로
--        "같은 타일이 길게 반복되는 구간"(= 창 배경)을 찾는다.
--        창 배경은 단일 플랫 타일이 넓게 깔리므로 눈에 띈다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local VR, BAT_COLS, BAT_ROWS = "VRAM1", 64, 32
local log = assert(io.open(OUTDIR .. "/batdump.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 30 do emu.frameadvance() end
pcall(client.setscreenshotosd, false)
pcall(client.screenshot, OUTDIR .. "/batdump_screen.png")

local function cell(r, c)
  local a = (r * BAT_COLS + c) * 2
  return memory.read_u8(a, VR) + memory.read_u8(a + 1, VR) * 256
end

say("행 | 화면y | 가장 긴 동일타일 런 (타일번호 x 길이 @ 시작칼럼) | 팔레트")
for r = 0, BAT_ROWS - 1 do
  local bestlen, besttile, bestc, bestpal = 0, -1, -1, -1
  local curlen, curtile, curstart = 0, -1, 0
  for c = 0, BAT_COLS - 1 do
    local e = cell(r, c)
    local t = e % 4096
    if t == curtile then
      curlen = curlen + 1
    else
      curtile, curlen, curstart = t, 1, c
    end
    if curlen > bestlen then
      bestlen, besttile, bestc, bestpal = curlen, curtile, curstart, math.floor(e / 4096)
    end
  end
  say(string.format("%2d | y=%3d | 타일$%03X x%2d @칼럼%2d | pal=%d",
      r, r * 8, besttile, bestlen, bestc, bestpal))
end

-- 대사창 후보: 긴 런이 연속으로 나타나는 행 구간을 요약
say("")
say("=== 화면 표시 범위 참고: 352x234 -> 칼럼 0..43, 행 0..28 ===")
log:close()
if client.exit then pcall(client.exit) end
