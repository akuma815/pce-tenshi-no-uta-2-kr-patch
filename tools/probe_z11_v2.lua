-- Z11 프로브 v2 — API 표면 열거 + gui 오류 노출 + 부팅부터 GETFNT 포착
local ROOT   = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUTDIR = ROOT .. [[\translation\z11_probe]]
local TAG    = "v2"
local BUDGET = 6000

local log = assert(io.open(OUTDIR .. "/v2_" .. TAG .. ".log", "w"))
local tsv = assert(io.open(OUTDIR .. "/v2_" .. TAG .. ".tsv", "w"))
tsv:write("frame\tsjis\tmode\tsrc_ptr\tdest\tn\n")
local function say(s) log:write(tostring(s) .. "\n"); log:flush(); console.log(tostring(s)) end

-- ---------- 0. API 표면 열거 ----------
local function dump(name, t)
  if type(t) ~= "table" then say("API " .. name .. " = " .. type(t)); return end
  local keys = {}
  for k, v in pairs(t) do keys[#keys+1] = tostring(k) end
  table.sort(keys)
  say("API " .. name .. " (" .. #keys .. "): " .. table.concat(keys, " "))
end
dump("gui", gui); dump("client", client); dump("savestate", savestate)
dump("emu", emu); dump("event", event)

-- ---------- 1. gui 호출별 성공/실패 개별 기록 ----------
local KO = "한글자막테스트 가나다 힣"
local gui_report = {}
local function try(label, fn, ...)
  local ok, err = pcall(fn, ...)
  if gui_report[label] == nil then
    gui_report[label] = ok and "OK" or ("ERR: " .. tostring(err))
    say("GUI " .. label .. " -> " .. gui_report[label])
  end
  return ok
end

local function draw()
  try("drawRectangle", gui.drawRectangle, 8, 150, 240, 44, 0xFF000000, 0xFF000000)
  try("text",          gui.text, 8, 8, "text:" .. KO)
  try("drawText",      gui.drawText, 12, 154, "dT:" .. KO, 0xFFFFFFFF, 0xFF000000, 12)
  try("drawText+font", gui.drawText, 12, 172, "MG:" .. KO, 0xFF00FF00, 0xFF000000, 12, "Malgun Gothic")
  try("drawString",    gui.drawString, 12, 120, "dS:" .. KO, 0xFFFFFF00, 0xFF000000, 12)
end

-- ---------- 2. GETFNT 훅 ----------
local pending, n_entry, n_copy = nil, 0, 0
local seen, first_frame = {}, nil
event.on_bus_exec(function()
  n_entry = n_entry + 1
  pending = { f = emu.framecount(),
              lead = memory.read_u8(0x2000 + 0xF8, "System Bus"),
              trail = memory.read_u8(0x2000 + 0xF9, "System Bus"),
              mode = memory.read_u8(0x2000 + 0xFF, "System Bus") }
end, 0xF124, "Z11 entry", "System Bus")

event.on_bus_exec(function()
  n_copy = n_copy + 1
  local function z(a) return memory.read_u8(0x2000 + a, "System Bus") end
  local src, dest = z(0xEC) + z(0xED) * 0x100, z(0xFA) + z(0xFB) * 0x100
  local p = pending or { f = emu.framecount(), lead = 0, trail = 0, mode = 0 }
  local sjis = string.format("%02X%02X", p.lead, p.trail)
  seen[sjis] = (seen[sjis] or 0) + 1
  first_frame = first_frame or p.f
  tsv:write(string.format("%d\t%s\t%02X\t%04X\t%04X\t%d\n", p.f, sjis, p.mode, src, dest, n_copy))
  if n_copy <= 30 then
    say(string.format("GETFNT #%d f%d sjis=%s mode=%02X src=%04X dest=%04X",
        n_copy, p.f, sjis, p.mode, src, dest))
  end
  pending = nil
end, 0xF1B9, "Z11 copy", "System Bus")

-- ---------- 3. 부팅부터 진행 ----------
pcall(client.speedmode, 400)
say("boot run, budget=" .. BUDGET)
local t0 = os.clock()
for f = 1, BUDGET do
  if f % 90 < 4 then pcall(joypad.set, { Run = true, I = true, II = true }, 1) end
  draw()
  emu.frameadvance()
  if f % 500 == 0 or f == 60 then
    pcall(client.screenshot, string.format("%s/v2_f%05d.png", OUTDIR, f))
    say(string.format("f%d entry=%d copy=%d", f, n_entry, n_copy))
  end
end
local wall = os.clock() - t0

-- 클라이언트 창 캡처(가능하면) — gui 레이어 포함 여부 판정
for _, nm in ipairs({"screenshotClient", "screenshotToClipboard"}) do
  if client[nm] then
    local ok, err = pcall(client[nm], string.format("%s/v2_client.png", OUTDIR))
    say("client." .. nm .. " -> " .. tostring(ok) .. " " .. tostring(err))
  else
    say("client." .. nm .. " = 없음")
  end
end

local uniq = 0; for _ in pairs(seen) do uniq = uniq + 1 end
say(string.format("RESULT entry=%d copy=%d uniq=%d first_frame=%s fps=%.1f",
    n_entry, n_copy, uniq, tostring(first_frame), BUDGET / math.max(wall, 0.001)))

local st = assert(io.open(OUTDIR .. "/v2_status.txt", "w"))
st:write(string.format("entry=%d\ncopy=%d\nuniq=%d\nfirst_frame=%s\nfps=%.1f\nverdict=%s\n",
    n_entry, n_copy, uniq, tostring(first_frame), BUDGET / math.max(wall, 0.001),
    n_copy > 0 and "P1_HIT" or "P1_MISS"))
for k, v in pairs(gui_report) do st:write("gui_" .. k .. "=" .. v .. "\n") end
st:close(); tsv:close(); log:close()
if client.exit then pcall(client.exit) elseif client.exitprogram then pcall(client.exitprogram) end
