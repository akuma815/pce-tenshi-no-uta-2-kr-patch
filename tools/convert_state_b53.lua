-- 빌드 간 퀵세이브 변환 (2026-10-11): b51 퀵세이브(씬 1730) → b53. 메모리에 올라온 장면 바이트 중 b51→b53 디스크 차이를 반영(주변 17바이트가
-- b51 디스크와 일치할 때만) + 스크래치 행 IBANK/IBASE 를 b53 카드 씬 테이블 값으로. 저장 후 PROBE_DIR 로 진행해 검증.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE")); local CONV = assert(os.getenv("PROBE_CONV")); local SAVE = assert(os.getenv("PROBE_SAVE"))
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/convert.log", "w")); local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local SS = "Super System Card RAM"
local function hex(dom, a, n) local t = {} for i = 0, n - 1 do t[#t + 1] = string.format("%02x", memory.read_u8(a + i, dom)) end return table.concat(t) end
local fh = assert(io.open(CONV, "r")); local pokes = fh:read("*l"); local row = fh:read("*l"); fh:close()
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE); emu.frameadvance()
local ok, skip, todo = 0, 0, {}
for idx, ctx, nb in pokes:gmatch("(%x+):(%x+):(%x+)") do      -- 먼저 전부 확인(연속 바이트를 고치면 다음 확인이 어긋나므로)
  local a = tonumber(idx, 16)
  local cur = hex(SS, a - 8, 17)
  if cur == ctx then todo[#todo + 1] = {a, tonumber(nb, 16)}; ok = ok + 1 else skip = skip + 1; say("skip " .. idx .. " ram=" .. cur .. " exp=" .. ctx) end
end
for _, w in ipairs(todo) do memory.write_u8(w[1], w[2], SS) end
say("pokes ok=" .. ok .. " skip=" .. skip)
local before = hex("TurboCD RAM", 0x88CC, 3)
for i = 4, 6 do memory.write_u8(0x88C8 + i, tonumber(row:sub(2 * i + 1, 2 * i + 2), 16), "TurboCD RAM") end
say("scratch row[4..6] " .. before .. " -> " .. hex("TurboCD RAM", 0x88CC, 3))
savestate.save(SAVE); say("saved " .. SAVE)
for f = 1, 900 do
  if f <= 16 then joypad.set({Right = true}, 1) end
  emu.frameadvance()
  if f % 60 == 0 then client.screenshot(OUT .. string.format("/c_%04d.png", f)) end
end
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
