-- $4036(벡터)/$4284(디스패처) 호출자 주소 히스토그램 (PCEHawk + 원본 디스크/무헤더 카드 + 사용자 세이브)
--   목적: 텍스트 프린터($92EE 등)가 아닌 스크립트 인터프리터의 호출을 구분해 조사 마커 게이트 근거 확보.
--   행 = 호출 1건: frame, kind(v/d), ret(스택 복귀주소), MPR6, 2E69, zp52/53/54/55, byte(=이 호출의 반환값 $2D80),
--   getfnt(다음 호출까지 GETFNT 횟수)
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\b22_runtime\callers]]
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
-- 입력: 타이틀 Run(≤900) → B1 펄스(이어하기, 기본 커서 슬롯) → 대사 넘김 B1(60f) → 메뉴/메모 → 걷기(전투)
local S0 = 2900
local script = {}
for k = 0, 39 do script[#script+1] = {S0 + k * 60, "B1", 3} end
local B = S0 + 2500
script[#script+1] = {B, "Run", 3}; script[#script+1] = {B + 90, "shot", "menu"}
for k = 0, 3 do script[#script+1] = {B + 120 + k * 30, "Down", 3} end
script[#script+1] = {B + 270, "B1", 3}; script[#script+1] = {B + 450, "shot", "memo_list"}
script[#script+1] = {B + 480, "B1", 3}; script[#script+1] = {B + 700, "shot", "memo_body"}
for k = 1, 6 do script[#script+1] = {B + 700 + k * 90, "B1", 3} end
for k = 1, 4 do script[#script+1] = {B + 1300 + k * 60, "B2", 3} end
local W = B + 1600
for f = 1, W + 5000 do
  local pad = {}
  if f > 400 and f <= 900 and f % 120 < 3 then pad.Run = true end
  if f > 900 and f < S0 and f % 120 < 3 then pad.B1 = true end
  for _, e in ipairs(script) do
    if e[2] == "shot" then if f == e[1] then shot(e[3]) end
    elseif f >= e[1] and f < e[1] + e[3] then pad[e[2]] = true end
  end
  if f >= W then
    local ph = ((f - W) // 150) % 4
    if ph == 0 then pad.Left = true elseif ph == 1 then pad.Up = true elseif ph == 2 then pad.Right = true else pad.Down = true end
    if f % 40 == 0 then pad.B2 = true end
    if f % 200 == 0 then pad.B1 = true end
  end
  pcall(joypad.set, pad, 1)
  emu.frameadvance()
  if f % 1000 == 0 then shot("walk"); say(string.format("f%d rows=%d", f, nrows)) end
end
flush(); say("done rows=" .. nrows); log:close(); tsv:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
