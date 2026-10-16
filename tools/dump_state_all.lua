-- 퀵세이브의 전 메모리 도메인 덤프 (2026-10-11 영상 싱크 A/B): PROBE_STATE 로드 직후 각 도메인을 PROBE_OUT/<도메인>.bin 으로.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE"))
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
for i = 1, 20 do emu.frameadvance() end
savestate.load(STATE)
local list = assert(io.open(OUT .. "/domains.txt", "w"))
for _, dom in ipairs(memory.getmemorydomainlist()) do
  local n = memory.getmemorydomainsize(dom)
  list:write(dom .. "\t" .. n .. "\n")
  if n <= 0x100000 and not dom:find("ROM") and not dom:find("System Bus") then
    local f = assert(io.open(OUT .. "/" .. dom:gsub("[^%w]", "_") .. ".bin", "wb")); local t = {}
    for i = 0, n - 1 do t[#t + 1] = string.char(memory.read_u8(i, dom)) end
    f:write(table.concat(t)); f:close()
  end
end
list:close()
local f = io.open(OUT .. "/dump.done", "w"); f:write("ok"); f:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
