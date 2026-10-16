-- Z11 진단 — 대사 텍스트가 스프라이트인가? (구현 아님, 판정만)
--  PCE SATB = VRAM 안 64엔트리 x 4워드.
--    word0 = Y(0..9bit), word1 = X(0..9bit), word2 = 패턴주소, word3 = 속성
--    화면좌표 = Y-64, X-32
--  DVSSR(R13)은 관측 불가하므로 VRAM 전역에서 SATB 후보를 점수화해 찾는다.
--  판정: 대사창 y(약 144~200) 대역에 몰린 스프라이트가 있으면 = 텍스트가 스프라이트.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local VR = "VRAM1"
local log = assert(io.open(OUTDIR .. "/satb.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 30 do emu.frameadvance() end          -- 대사 화면 안정화
pcall(client.setscreenshotosd, false)
pcall(client.screenshot, OUTDIR .. "/satb_screen.png")

local function w(addr)                            -- 워드주소 -> 값
  local a = addr * 2
  return memory.read_u8(a, VR) + memory.read_u8(a + 1, VR) * 256
end

-- ---------- SATB 후보 점수화 ----------
local best, bestscore = nil, -1
local cands = {}
for base = 0, 0x8000 - 256, 64 do                 -- 64워드 간격으로 훑는다
  local ok, plaus, nonzero = true, 0, 0
  for i = 0, 63 do
    local y = w(base + i*4) % 1024
    local x = w(base + i*4 + 1) % 1024
    if y ~= 0 or x ~= 0 then nonzero = nonzero + 1 end
    local sy, sx = y - 64, x - 32
    if sy >= -32 and sy <= 260 and sx >= -32 and sx <= 400 then plaus = plaus + 1 end
  end
  local score = plaus + nonzero
  if nonzero >= 8 and plaus >= 40 then
    cands[#cands+1] = { base = base, plaus = plaus, nonzero = nonzero, score = score }
  end
  if score > bestscore then bestscore, best = score, base end
end
table.sort(cands, function(a, b) return a.score > b.score end)
say(string.format("SATB 후보 %d개 (nonzero>=8 & plausible>=40)", #cands))
for i = 1, math.min(8, #cands) do
  local c = cands[i]
  say(string.format("  후보%d base=$%04X(워드)  유효좌표%d/64  비영엔트리%d",
      i, c.base, c.plaus, c.nonzero))
end

-- ---------- 상위 후보의 엔트리를 화면좌표로 덤프 ----------
local function dump(base, tag)
  say(string.format("--- %s base=$%04X ---", tag, base))
  local inwin, total = 0, 0
  for i = 0, 63 do
    local y  = w(base + i*4) % 1024
    local x  = w(base + i*4 + 1) % 1024
    local pt = w(base + i*4 + 2)
    local at = w(base + i*4 + 3)
    local sy, sx = y - 64, x - 32
    if y ~= 0 or x ~= 0 then
      total = total + 1
      local mark = ""
      if sy >= 130 and sy <= 215 then inwin = inwin + 1; mark = "   <== 대사창 y대역" end
      if total <= 26 then
        say(string.format("  #%02d  화면(%4d,%4d)  패턴$%04X  속성$%04X%s",
            i, sx, sy, pt, at, mark))
      end
    end
  end
  say(string.format("  => 비영 스프라이트 %d개 중 대사창 y대역(130~215) %d개", total, inwin))
  return total, inwin
end

if #cands > 0 then
  for i = 1, math.min(3, #cands) do
    dump(cands[i].base, "후보" .. i)
  end
else
  say("후보 없음 — 최고점 base=$" .. string.format("%04X", best))
  dump(best, "최고점")
end

-- ---------- 참고: 관례적 위치도 함께 ----------
for _, b in ipairs({ 0x7F00, 0x7000, 0x6000 }) do
  dump(b, string.format("관례후보 $%04X", b))
end

log:close()
if client.exit then pcall(client.exit) end
