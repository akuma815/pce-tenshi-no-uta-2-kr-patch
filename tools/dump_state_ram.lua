-- 퀵세이브의 메모리 덤프 (2026-10-11): Super System Card RAM 전체 + 스크래치 행($88C8, 42B) → PROBE_OUT. 빌드 간 퀵세이브 변환에서 상주 씬 식별용.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE); emu.frameadvance()
local function dump(dom, a, n, path) local f = assert(io.open(path, "wb")); local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.char(memory.read_u8(a + i, dom)) end; f:write(table.concat(t)); f:close() end
dump("Super System Card RAM", 0, memory.getmemorydomainsize("Super System Card RAM"), OUT .. "/sscram.bin")
dump("TurboCD RAM", 0, memory.getmemorydomainsize("TurboCD RAM"), OUT .. "/cdram.bin")
client.screenshot(OUT .. "/at_load.png")
local f = io.open(OUT .. "/dump.done", "w"); f:write("ok"); f:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
