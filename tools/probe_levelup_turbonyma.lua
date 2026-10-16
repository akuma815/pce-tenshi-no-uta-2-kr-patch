-- 레벨업 실험: 사본 스테이트 로드 → 매 프레임 HP/MP=최대, EXP=60000 → 던전 왕복으로 전투 유발, I 연타로 전투 → 레벨·스탯 기록
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\b31_runtime\]]
local D = "Main Memory"
local log = assert(io.open(OUT .. "levelup.log", "w"))
local function say(x) log:write(tostring(x) .. "\n"); log:flush() end
local function r(a) return memory.read_u8(a, D) end
local function w(a, v) memory.write_u8(a, v, D) end
local function cheat(exp)
  for i = 0, 3 do
    w(0x1D7F + i, r(0x1D87 + i)); w(0x1D83 + i, r(0x1D8B + i))
    w(0x1D8F + i, r(0x1D97 + i)); w(0x1D93 + i, r(0x1D9B + i))
    if exp then w(0x1D67 + i, exp % 256); w(0x1D6B + i, (exp // 256) % 256); w(0x1D6F + i, exp // 65536) end
  end
end
local function stat()
  local t = {}
  for i = 0, 3 do t[#t+1] = string.format("L%d HPmax%d MPmax%d exp%d next%d", r(0x1D63+i)+1, r(0x1D87+i)+r(0x1D8B+i)*256, r(0x1D97+i)+r(0x1D9B+i)*256, r(0x1D67+i)+r(0x1D6B+i)*256+r(0x1D6F+i)*65536, r(0x1D73+i)+r(0x1D77+i)*256+r(0x1D7B+i)*65536) end
  return table.concat(t, " | ")
end
pcall(function() client.speedmode(800) end)
for i = 1, 60 do emu.frameadvance() end
savestate.load(OUT .. "user_qs1_2151.State")
for i = 1, 3 do emu.frameadvance() end
say("start: " .. stat())
local EXP = tonumber(os.getenv("CHEAT_EXP") or "16000000")
local last = stat()
local dmg, mpuse = 0, 0
for f = 1, 6000 do
  for i = 0, 3 do
    if r(0x1D7F+i)+r(0x1D83+i)*256 < r(0x1D87+i)+r(0x1D8B+i)*256 then dmg = dmg + 1 end
    if r(0x1D8F+i)+r(0x1D93+i)*256 < r(0x1D97+i)+r(0x1D9B+i)*256 then mpuse = mpuse + 1 end
  end
  cheat(f < 10 and EXP or nil)
  local ph = (f // 40) % 2
  local pad = {}
  if ph == 0 then pad.Left = true else pad.Right = true end
  if f % 20 < 3 then pad.I = true end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  if f % 120 == 0 then local s = stat(); if s ~= last then say("f" .. f .. ": " .. s); last = s end end
  if f % 1500 == 0 then pcall(client.screenshot, OUT .. string.format("lv_%05d.png", f)) end
end
say("damage events caught (HP below max before rewrite): " .. dmg .. ", MP use events: " .. mpuse)
say("end: " .. stat()); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
