-- Z11 프로브 v3 — $967E(게임 렌더러) vs $F124(BIOS 폴백) 커버리지 비교
--                + emucore 표면 gui 렌더(P3) + 문자 코드 위치 탐색
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local BUDGET = 4200

local log = assert(io.open(OUTDIR .. "/v3.log", "w"))
local tsv = assert(io.open(OUTDIR .. "/v3.tsv", "w"))
tsv:write("hook\tframe\tA\tX\tY\tMPR4\tzpF8\tzpF9\tzpFF\tzpEC\tzpED\tzpFA\tzpFB\n")
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end
local function z(a) return memory.read_u8(0x2000 + a, "System Bus") end

local n = { g = 0, b = 0 }          -- g = $967E, b = $F124
local seen = { g = {}, b = {} }

local function rec(tag, key)
  n[key] = n[key] + 1
  local A  = emu.getregister("A")  or 0
  local X  = emu.getregister("X")  or 0
  local Y  = emu.getregister("Y")  or 0
  local M4 = emu.getregister("MPR-4") or 0
  local f8, f9, ff = z(0xF8), z(0xF9), z(0xFF)
  seen[key][string.format("%02X%02X", f8, f9)] = true
  if n[key] <= 300 then
    tsv:write(string.format("%s\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      tag, emu.framecount(), A, X, Y, M4, f8, f9, ff, z(0xEC), z(0xED), z(0xFA), z(0xFB)))
  end
  if n[key] <= 12 then
    say(string.format("%s #%d f%d A=%02X X=%02X Y=%02X MPR4=%02X zp[F8F9]=%02X%02X FF=%02X",
      tag, n[key], emu.framecount(), A, X, Y, M4, f8, f9, ff))
  end
end

event.on_bus_exec(function() rec("GAME_967E", "g") end, 0x967E, "Z11 game renderer", "System Bus")
event.on_bus_exec(function() rec("BIOS_F124", "b") end, 0xF124, "Z11 bios getfnt",   "System Bus")

-- ---------- P3: emucore 표면에 그리기 ----------
local KO = "한글자막 가나다 힣 테스트"
local surf_ok = pcall(gui.use_surface, "emucore")
say("gui.use_surface('emucore') -> " .. tostring(surf_ok))
pcall(client.setscreenshotosd, true)

local function draw()
  pcall(gui.use_surface, "emucore")
  pcall(gui.drawRectangle, 6, 140, 244, 52, 0xFF101010, 0xFF101010)
  pcall(gui.drawText,   10, 144, "dT " .. KO, 0xFFFFFFFF, 0xFF000000, 11)
  pcall(gui.drawText,   10, 162, "MG " .. KO, 0xFF66FF66, 0xFF000000, 11, "Malgun Gothic")
  pcall(gui.drawString, 10, 178, "dS " .. KO, 0xFFFFFF66, 0xFF000000, 11, "Gulim")
  pcall(gui.text,        6,   6, "guitext " .. KO)
end

pcall(client.speedmode, 400)
local t0 = os.clock()
for f = 1, BUDGET do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  draw()
  emu.frameadvance()
  if f % 700 == 0 or f == 3000 then
    pcall(client.screenshot, string.format("%s/v3_f%05d.png", OUTDIR, f))
    say(string.format("f%d  967E=%d  F124=%d", f, n.g, n.b))
  end
end
local wall = os.clock() - t0

local function cnt(t) local c=0 for _ in pairs(t) do c=c+1 end return c end
say(string.format("RESULT 967E=%d (uniq %d)  F124=%d (uniq %d)  fps=%.1f",
    n.g, cnt(seen.g), n.b, cnt(seen.b), BUDGET/math.max(wall,0.001)))

local st = assert(io.open(OUTDIR .. "/v3_status.txt", "w"))
st:write(string.format("hits_967E=%d\nuniq_967E=%d\nhits_F124=%d\nuniq_F124=%d\nfps=%.1f\nsurface_emucore=%s\nratio=%s\n",
  n.g, cnt(seen.g), n.b, cnt(seen.b), BUDGET/math.max(wall,0.001), tostring(surf_ok),
  n.b > 0 and string.format("%.2f", n.g / n.b) or "n/a"))
st:close(); tsv:close(); log:close()
if client.exit then pcall(client.exit) end
