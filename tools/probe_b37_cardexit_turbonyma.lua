-- b37/b38 카드 게임 종료 재현 (PROBE_STATE = 결과 화면 상태, PROBE_POKE_RET=1 이면 모듈 복귀 주소를 $C89E 로 포크) (2026-10-11): 사용자 퀵세이브(결과 화면 「계속할까요? Y/N」) 로드 → N → 모듈 종료 → 대화.
-- PRESENT/FLAG/TBANK, 스크래치 행(IBANK/IBASE), 씬 770 서명(Super System Card RAM 0x1A20C)을 기록. tools/run_focused_probe.ps1 로 실행(포커스+클릭 후 신호 파일).
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT = assert(os.getenv("PROBE_OUT"), "PROBE_OUT 미지정")
local STATE = os.getenv("PROBE_STATE") or (ROOT .. [[\BizHawk-master\output\PC Engine\State\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b37.TurboNyma.QuickSave1.State]])
local FOCUS_FLAG = [[C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\4810c544-ca01-4c35-9ec3-049a276c76c9\scratchpad\focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "\\cardexit.log", "w"))
local function say(s) log:write(tostring(s) .. "\n"); log:flush() end
local function cd(a) return memory.read_u8(a, "TurboCD RAM") end
local function hex(dom, a, n) local t = {} for i = 0, n - 1 do t[#t + 1] = string.format("%02X", memory.read_u8(a + i, dom)) end return table.concat(t, " ") end
local function st() return string.format("PRESENT=%02X FLAG=%02X TBANK=%02X IBANK=%02X IBASE=%02X", cd(0x88FE), cd(0x88F9), cd(0x88FA), cd(0x88CC), cd(0x88CD)) end
pcall(function() client.speedmode(400) end)
for i = 1, 30 do emu.frameadvance() end
savestate.load(STATE)
for i = 1, 5 do emu.frameadvance() end
if os.getenv("PROBE_POKE_RET") == "1" then memory.write_u8(0x1CBC, 0x9E, "TurboCD RAM"); memory.write_u8(0x1CBD, 0xC8, "TurboCD RAM") end   -- b29 이전 상태: 모듈 RAM 의 복귀 주소를 패치값으로
say("loaded: " .. st() .. " ret=" .. hex("TurboCD RAM", 0x1CBC, 2))
local seq = {{"Right", 3}, {nil, 20}, {"I", 3}, {nil, 600}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}, {"I", 3}, {nil, 200}}
local last = ""; local f0 = emu.framecount(); local dumped = false
for _, step in ipairs(seq) do
  for f = 1, step[2] do
    if step[1] then joypad.set({[step[1]] = true}, 1) end
    emu.frameadvance()
    local s = st(); if s ~= last then say(string.format("f%d %s", emu.framecount() - f0, s)); last = s end
    local stub = hex("TurboCD RAM", 0x889F, 3)
    if not dumped and stub == "43 20 48" then   -- 엔진 재적재 감지 (스텁 TMA5 PHA)
      dumped = true
      say(string.format("f%d engine back: stub=%s sig770=%s scratch=%s", emu.framecount() - f0, hex("TurboCD RAM", 0x889F, 16),
        hex("Super System Card RAM", (0x75 - 0x68) * 0x2000 + 0x120C, 16), hex("TurboCD RAM", 0x88C8, 42)))
    end
    if (emu.framecount() - f0) % 60 == 0 then client.screenshot(OUT .. string.format("\\exit_%04d.png", emu.framecount() - f0)) end
  end
end
say("final: " .. st() .. " scratch=" .. hex("TurboCD RAM", 0x88C8, 42) .. " dec=" .. hex("TurboCD RAM", 0x88F6, 3))
say("done"); log:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
