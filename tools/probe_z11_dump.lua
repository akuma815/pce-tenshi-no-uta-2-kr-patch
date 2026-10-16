-- Z11 지상검증 1단계 — 원자재 덤프
--  대사가 떠 있는 순간의 VRAM + 팔레트 + 스크린샷을 같은 시점에 남긴다.
--  이후 파이썬이 이 원자재로 화면을 재현해 정답 기하를 역산한다.
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe\gt]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]
local log = assert(io.open(OUTDIR .. "/dump.log", "w"))
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

for i = 1, 20 do emu.frameadvance() end
say("state load: " .. tostring(pcall(function() savestate.load(STATE) end)))
for i = 1, 40 do emu.frameadvance() end          -- 대사 화면 안정화

local function dump_domain(dom, size, name)
  local ok, a = pcall(memory.read_bytes_as_array, 0, size, dom)
  if not ok then say("덤프 실패: " .. dom); return false end
  local f = assert(io.open(OUTDIR .. "/" .. name, "wb"))
  local buf, n = {}, 0
  for i = 1, size do
    buf[#buf+1] = string.char(a[i] or a[i-1] or 0)
    n = n + 1
    if #buf >= 4096 then f:write(table.concat(buf)); buf = {} end
  end
  if #buf > 0 then f:write(table.concat(buf)) end
  f:close()
  say(string.format("덤프 %s : %d 바이트 -> %s", dom, n, name))
  return true
end

-- 스크린샷은 오버레이 없이 (순수 게임 화면 = 정답지)
pcall(client.setscreenshotosd, false)
pcall(client.screenshot, OUTDIR .. "/screen.png")

dump_domain("VRAM1", 65536, "vram.bin")
dump_domain("VCEPalette", 1024, "palette.bin")

-- 참고 정보
say("framecount=" .. emu.framecount())
for _, r in ipairs({"MPR-0","MPR-1","MPR-2","MPR-3","MPR-4","MPR-5","MPR-6","MPR-7"}) do
  say(string.format("  %s=%s", r, tostring(emu.getregister(r))))
end
say("done")
log:close()
if client.exit then pcall(client.exit) end
