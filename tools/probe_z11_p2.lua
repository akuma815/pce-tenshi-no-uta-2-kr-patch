-- Z11 P2 — 초상화 대사가 렌더 훅에 잡히는가 (설계 생사 판정)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local STATE  = ROOT .. [[\BizHawk-master\output\PC Engine\State\diag_portrait_pcehawk.State]]

local log = assert(io.open(OUTDIR .. "/p2.log", "w"))
local tsv = assert(io.open(OUTDIR .. "/p2.tsv", "w"))
tsv:write("hook\tn\tframe\tsjis\tzp52\tzp53\tzp54\tzp55\n")
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end
local function z(a) return memory.read_u8(0x2000 + a, "System Bus") end

local n = { g = 0, b = 0 }
local text = { g = {}, b = {} }

local function rec(tag, key)
  n[key] = n[key] + 1
  local s = string.format("%02X%02X", z(0xF9), z(0xF8))
  text[key][#text[key]+1] = s
  if n[key] <= 400 then
    tsv:write(string.format("%s\t%d\t%d\t%s\t%02X\t%02X\t%02X\t%02X\n",
      tag, n[key], emu.framecount(), s, z(0x52), z(0x53), z(0x54), z(0x55)))
  end
end

for i = 1, 20 do emu.frameadvance() end
local ok, err = pcall(function() savestate.load(STATE) end)
say("state load: " .. tostring(ok) .. " " .. tostring(err))
n.g, n.b, text.g, text.b = 0, 0, {}, {}      -- 로드 시점 기준으로 초기화

-- ★ 훅은 반드시 savestate.load 이후에 등록한다.
--   상태 로드가 코어를 재생성하면서 기존 on_bus_exec 등록을 떨어뜨린다(실측).
event.on_bus_exec(function() rec("GAME_967E","g") end, 0x967E, "P2 game", "System Bus")
event.on_bus_exec(function() rec("BIOS_F124","b") end, 0xF124, "P2 bios", "System Bus")
say("훅 등록 완료 (상태 로드 이후)")

pcall(client.speedmode, 200)
pcall(client.screenshot, OUTDIR .. "/p2_f0000_onload.png")

for f = 1, 900 do
  if f % 120 < 3 then pcall(joypad.set, { I = true }, 1) end
  emu.frameadvance()
  if f == 30 or f == 200 or f == 450 or f == 700 or f == 900 then
    pcall(client.screenshot, string.format("%s/p2_f%04d.png", OUTDIR, f))
    say(string.format("f%d  967E=%d  F124=%d", f, n.g, n.b))
  end
end

say("SJIS(967E): " .. table.concat(text.g, ""))
say(string.format("RESULT 967E=%d  F124=%d", n.g, n.b))
local st = assert(io.open(OUTDIR .. "/p2_status.txt", "w"))
st:write(string.format("hits_967E=%d\nhits_F124=%d\nverdict=%s\nsjis=%s\n",
  n.g, n.b, n.g > 0 and "P2_PASS" or "P2_FAIL", table.concat(text.g, "")))
st:close(); tsv:close(); log:close()
if client.exit then pcall(client.exit) end
