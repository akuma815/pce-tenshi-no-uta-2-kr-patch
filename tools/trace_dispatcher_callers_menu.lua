-- $4036(벡터)/$4284(디스패처) 호출자 주소 히스토그램 (PCEHawk + 원본 디스크/무헤더 카드 + 사용자 세이브)
--   목적: 텍스트 프린터($92EE 등)가 아닌 스크립트 인터프리터의 호출을 구분해 조사 마커 게이트 근거 확보.
--   행 = 호출 1건: frame, kind(v/d), ret(스택 복귀주소), MPR6, 2E69, zp52/53/54/55, byte(=이 호출의 반환값 $2D80),
--   getfnt(다음 호출까지 GETFNT 횟수)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime\callers_menu]]
local BUS = "System Bus"
local log = assert(io.open(OUTDIR .. "/callers.log", "w"))
local tsv = assert(io.open(OUTDIR .. "/callers.tsv", "w"))
tsv:write("frame\tkind\tret\tmpr6\tv2E69\tzp52\tzp53\tzp54\tzp55\tbyte\tgetfnt\n")
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function rd(a) return memory.read_u8(a, BUS) end
local function z(a) return rd(0x2000 + a) end
local function reg(n) local v = emu.getregister(n); return v or -1 end
local cur, getfnt, nrows, inner = nil, 0, 0, false
local function flush()
  if cur then
    cur.byte = rd(0x2D80); cur.getfnt = getfnt
    tsv:write(string.format("%d\t%s\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\n",
      cur.frame, cur.kind, cur.ret, cur.mpr6, cur.v2E69, cur.zp52, cur.zp53, cur.zp54, cur.zp55, cur.byte, cur.getfnt))
    nrows = nrows + 1
  end
  cur, getfnt = nil, 0
end
local function start(kind)
  local s = reg("S"); if s < 0 then s = reg("SP") end
  local ret = rd(0x2100 + ((s + 1) % 256)) + rd(0x2100 + ((s + 2) % 256)) * 256
  flush()
  cur = { frame = emu.framecount(), kind = kind, ret = ret, mpr6 = reg("MPR-6"), v2E69 = rd(0x2E69),
          zp52 = z(0x52), zp53 = z(0x53), zp54 = z(0x54), zp55 = z(0x55) }
end
event.on_bus_exec(function() start("v"); inner = true end, 0x4036, "vec", BUS)
event.on_bus_exec(function() if inner then inner = false else start("d") end end, 0x4284, "disp", BUS)
event.on_bus_exec(function() getfnt = getfnt + 1 end, 0x967E, "getfnt", BUS)
say("S reg probe: S=" .. tostring(reg("S")) .. " SP=" .. tostring(reg("SP")))
pcall(function() client.speedmode(400) end)
local shots = 0
local function shot(n) pcall(client.screenshot, string.format("%s/tr_%s_f%05d.png", OUTDIR, n, emu.framecount())) end
-- MODE=menu: 로드 화면에서 Up→B1 로 슬롯 1(도시, 대사 없음) → 메뉴 순회(마법/상태/도구/장비/메모 본문)
local script = {}
local function seq(t0, keys)  -- keys = {{dt,"btn"},...}
  for _, k in ipairs(keys) do script[#script+1] = {t0 + k[1], k[2], 3} end
end
local S0 = 2600
seq(S0, {{0,"Run"},{90,"shot:menu"},{120,"B1"},{300,"shot:magic"},{330,"B1"},{450,"shot:magic2"},{480,"B2"},{510,"B2"},
  {600,"Right"},{630,"B1"},{780,"shot:status"},{810,"B1"},{900,"shot:status2"},{930,"B2"},{960,"B2"},
  {1050,"Down"},{1080,"B1"},{1230,"shot:item"},{1260,"B1"},{1350,"shot:item2"},{1380,"B2"},{1410,"B2"},{1440,"B2"},
  {1530,"Right"},{1560,"B1"},{1710,"shot:equip"},{1740,"B1"},{1830,"shot:equip2"},{1860,"B2"},{1890,"B2"},{1920,"B2"},
  {2010,"Down"},{2040,"Left"},{2070,"B1"},{2250,"shot:memo_list"},{2280,"B1"},{2460,"shot:memo_body"},
  {2550,"B1"},{2640,"B1"},{2730,"B1"},{2820,"B1"},{2910,"shot:memo_body2"},{3000,"B2"},{3060,"B2"},{3120,"B2"},
  {3210,"Down"},{3240,"Right"},{3270,"B1"},{3450,"shot:load"},{3480,"B2"},{3540,"B2"}})
local W = S0 + 3700
for f = 1, W + 300 do
  local pad = {}
  if f > 400 and f <= 900 and f % 120 < 3 then pad.Run = true end
  if f > 900 and f < S0 and f % 120 < 3 then pad.Up = true end
  if f > 900 and f < S0 and f % 120 >= 60 and f % 120 < 63 then pad.B1 = true end
  for _, e in ipairs(script) do
    if e[2]:sub(1,5) == "shot:" then if f == e[1] then shot(e[2]:sub(6)) end
    elseif f >= e[1] and f < e[1] + e[3] then pad[e[2]] = true end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  if f % 1000 == 0 then shot("walk"); say(string.format("f%d rows=%d", f, nrows)) end
end
flush(); say("done rows=" .. nrows); log:close(); tsv:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
