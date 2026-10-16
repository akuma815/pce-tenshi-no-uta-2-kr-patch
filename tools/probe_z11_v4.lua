-- Z11 프로브 v4 (P6) — $967E 호출 시점의 제로페이지 전체를 떠서
--                      "글자 커서" 변수를 찾는다 + 메모리 도메인 열거
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local BUDGET = 6000
local MAXROW = 400

local log = assert(io.open(OUTDIR .. "/v4.log", "w"))
local tsv = assert(io.open(OUTDIR .. "/v4_zp.tsv", "w"))
tsv:write("n\tframe\tsjis\tA\tX\tY\tzp_hex\n")
local function say(s) log:write(tostring(s).."\n"); log:flush(); console.log(tostring(s)) end

-- 메모리 도메인 열거 (팔레트 접근 가능성 확인)
local ok, doms = pcall(memory.getmemorydomainlist)
if ok and doms then
  local t = {}
  for i = 0, (#doms or 0) do if doms[i] then t[#t+1] = tostring(doms[i]) end end
  for _, v in pairs(doms) do t[#t+1] = tostring(v) end
  local uniq, out = {}, {}
  for _, v in ipairs(t) do if not uniq[v] then uniq[v]=true; out[#out+1]=v end end
  say("DOMAINS: " .. table.concat(out, " | "))
end

local n = 0
event.on_bus_exec(function()
  n = n + 1
  if n > MAXROW then return end
  local zp = memory.read_bytes_as_array(0x2000, 256, "System Bus")
  local h = {}
  for i = 1, 256 do h[i] = string.format("%02X", zp[i] or zp[i-1] or 0) end
  local lo = zp[0xF8 + 1] or 0
  local hi = zp[0xF9 + 1] or 0
  tsv:write(string.format("%d\t%d\t%04X\t%02X\t%02X\t%02X\t%s\n",
    n, emu.framecount(), hi * 256 + lo,
    emu.getregister("A") or 0, emu.getregister("X") or 0, emu.getregister("Y") or 0,
    table.concat(h)))
end, 0x967E, "Z11 zp dump", "System Bus")

pcall(client.speedmode, 400)
say("v4 start budget=" .. BUDGET)
for f = 1, BUDGET do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  emu.frameadvance()
  if f % 1000 == 0 then
    pcall(client.screenshot, string.format("%s/v4_f%05d.png", OUTDIR, f))
    say(string.format("f%d hits=%d", f, n))
  end
end
say("RESULT hits=" .. n)
local st = assert(io.open(OUTDIR .. "/v4_status.txt", "w"))
st:write("hits=" .. n .. "\nrows=" .. math.min(n, MAXROW) .. "\n")
st:close(); tsv:close(); log:close()
if client.exit then pcall(client.exit) end
