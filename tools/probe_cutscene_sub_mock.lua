-- 컷신 자막 PoC 1단계 = 화면 목업 (2026-10-14, PCEHawk): 사용자 퀵세이브 → 아래로 걸어 컷신 → PROBE_FROM 프레임부터
-- 빈 VRAM($0800-$0DFF) 에 자막 패턴(make_cutscene_sub_sprites.py), 스프라이트 팔레트 15 = 흰/검, SAT 57-62(RAM 이중 버퍼 $2432/$2632 + VRAM $0E00) 에 32x32 스프라이트 6개.
-- 게임이 그 칸을 덮어쓰는지 매 프레임 확인(쓰기 직전 값 비교)해 log 에 남긴다.
local OUT = assert(os.getenv("PROBE_OUT")); local STATE = assert(os.getenv("PROBE_STATE")); local PAT = assert(os.getenv("PROBE_PAT"))
local TOTAL = tonumber(os.getenv("PROBE_TOTAL") or "1800"); local FROM = tonumber(os.getenv("PROBE_FROM") or "760")
local WALK = tonumber(os.getenv("PROBE_WALK") or "400"); local SHOT = tonumber(os.getenv("PROBE_SHOT") or "20")
local FOCUS_FLAG = [[C:/Users/akuma/AppData/Local/Temp/claude/g--Downloads-Korean-Traslate-Project/4810c544-ca01-4c35-9ec3-049a276c76c9/scratchpad/focus.flag]]
client.pause()
while true do local fh = io.open(FOCUS_FLAG, "r"); if fh then fh:close(); break end; emu.yield() end
client.unpause()
local log = assert(io.open(OUT .. "/log.txt", "w")); local function say(s) log:write(s .. "\n"); log:flush() end
local fh = assert(io.open(PAT, "rb")); local pat = fh:read("*a"); fh:close()
for i = 1, 10 do emu.frameadvance() end
savestate.load(STATE); say("loaded, pattern bytes " .. #pat)
local function w16(dom, a, v) memory.write_u8(a, v & 0xFF, dom); memory.write_u8(a + 1, (v >> 8) & 0xFF, dom) end
local function r16(dom, a) return memory.read_u8(a, dom) | (memory.read_u8(a + 1, dom) << 8) end
local ENT = {}
for s = 0, 5 do ENT[s] = { 64 + 174, 64 + 32 * s, (0x20 + 4 * s) * 2, 0x118F } end
local overw = 0
local palw = 0
for f = 1, TOTAL do
  if f <= WALK then joypad.set({Down = true}, 1) end
  if f >= FROM then
    local need = (f == FROM)
    if f > FROM and r16("VCEPalette", 0x3E2) ~= 0x1FF then palw = palw + 1; need = true; if palw <= 5 then say(string.format("f%d palette15 color1 reset to %03X", f, r16("VCEPalette", 0x3E2))) end end
    if need or (f - FROM) % 120 == 0 then
      for i = 1, #pat do memory.write_u8(0x1000 + i - 1, pat:byte(i), "VRAM1") end
      w16("VCEPalette", 0x3E0, 0x000); w16("VCEPalette", 0x3E2, 0x1FF); w16("VCEPalette", 0x3E4, 0x000)
      -- PCEHawk 는 VDC 포트 쓰기 때만 스프라이트 디코드 캐시를 갱신 → 도메인 직접 쓰기 뒤 코어 상태 저장·재적재로 캐시 재구성(목업 전용 우회)
      local id = memorysavestate.savecorestate(); memorysavestate.loadcorestate(id); memorysavestate.removestate(id)
    end
    for s = 0, 5 do
      for _, base in ipairs({ { "Main Memory", 0x432 }, { "Main Memory", 0x632 }, { "VRAM1", 0x1C00 } }) do
        local a = base[2] + (57 + s) * 8
        if f > FROM and base[1] == "Main Memory" and r16(base[1], a) ~= ENT[s][1] then overw = overw + 1; if overw <= 10 then say(string.format("f%d overwritten %s+%X = %04X", f, base[1], a, r16(base[1], a))) end end
        for k = 1, 4 do w16(base[1], a + (k - 1) * 2, ENT[s][k]) end
      end
    end
  end
  emu.frameadvance()
  if f % SHOT == 0 and f >= FROM - 40 then client.screenshot(OUT .. string.format("/s_%05d.png", f)) end
  if f == FROM + 300 then savestate.save(OUT .. "/mock.State") end
end
say("overwrites " .. overw .. " palette resets " .. palw); say("done"); log:close()
local d = io.open(OUT .. "/done", "w"); d:write("ok"); d:close()
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
