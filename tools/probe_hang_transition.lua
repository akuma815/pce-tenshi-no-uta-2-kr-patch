-- 장면 전환 멈춤 재현 (2026-10-11 b51 게이트: 퀵세이브 1 → 오른쪽 한 칸(계단) → 검은 화면에서 돌아오지 않음).
-- PROBE_STATE 로드 → PROBE_DIR(기본 Right) 를 PROBE_HOLD 프레임 → PROBE_WAIT 프레임 관찰. 30프레임마다 스크린샷, 상태 변화 기록.
local OUT = assert(os.getenv("PROBE_OUT"), "PROBE_OUT 미지정")
local STATE = assert(os.getenv("PROBE_STATE"), "PROBE_STATE 미지정")
local DIR = os.getenv("PROBE_DIR") or "Right"
local HOLD = tonumber(os.getenv("PROBE_HOLD") or "16")
local WAIT = tonumber(os.getenv("PROBE_WAIT") or "1800")
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/hang.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
local function hex(dom, a, n) local t = {} for i = 0, n - 1 do t[#t + 1] = string.format("%02X", memory.read_u8(a + i, dom)) end return table.concat(t, " ") end
local function regs() local ok, r = pcall(function() return emu.getregisters() end); if not ok or not r then return {} end; return r end
local function pc() local r = regs(); for k, v in pairs(r) do if string.upper(k):find("PC") then return v end end; return -1 end
local function st() return string.format("PRESENT=%02X FLAG=%02X TBANK=%02X IBANK=%02X stub=%s", cd(0x88FE), cd(0x88F9), cd(0x88FA), cd(0x88CC), hex("TurboCD RAM", 0x889F, 3)) end
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE)
emu.frameadvance()
say("loaded " .. st() .. " scratch=" .. hex("TurboCD RAM", 0x88C8, 42))
-- PROBE_POKE = "주소=헥스;주소=헥스" (Super System Card RAM 도메인 인덱스, 16진) — 패치 전/후 바이트 기록
local POKE = os.getenv("PROBE_POKE")
if POKE and POKE ~= "" then
  for a, h in POKE:gmatch("(%x+)=(%x+)") do
    local addr = tonumber(a, 16)
    say(string.format("poke %X before %s", addr, hex("Super System Card RAM", addr, #h // 2)))
    for i = 0, #h // 2 - 1 do memory.write_u8(addr + i, tonumber(h:sub(2 * i + 1, 2 * i + 2), 16), "Super System Card RAM") end
    say(string.format("poke %X after  %s", addr, hex("Super System Card RAM", addr, #h // 2)))
  end
end
client.screenshot(OUT .. "/s_0000.png")
local f0 = emu.framecount(); local last = ""; local pcs = {}
for f = 1, HOLD + WAIT do
  if f <= HOLD then joypad.set({[DIR] = true}, 1) end
  emu.frameadvance()
  local s = st(); if s ~= last then say(string.format("f%d %s", f, s)); last = s end
  if f % 30 == 0 then client.screenshot(OUT .. string.format("/s_%04d.png", f)) end
  if f > HOLD + WAIT - 120 then for _ = 1, 1 do local p = pc(); pcs[p] = (pcs[p] or 0) + 1 end end
end
local t = {} for k, v in pairs(pcs) do t[#t + 1] = string.format("%04X:%d", k, v) end
say("PC(last 120f) " .. table.concat(t, " "))
local rr = {} for k, v in pairs(regs()) do rr[#rr + 1] = k .. "=" .. string.format("%X", v) end; table.sort(rr); say("regs " .. table.concat(rr, " "))
say("MPR? stack=" .. hex("Main Memory", 0x0100, 0x100))
say("final " .. st() .. " scratch=" .. hex("TurboCD RAM", 0x88C8, 42))
say("zp20=" .. hex("Main Memory", 0x0000, 0x60))
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
