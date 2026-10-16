-- PCEHawk(원본 디스크) QuickSave3(카드판) → II(카드 보기) → VRAM/팔레트/TurboCD RAM 덤프를 s8 로 저장 + 스크린샷
local ROOT = [[G:\Downloads\Korean Traslate Project\Games\Tenshi no Uta II - Datenshi no Sentaku (Japan)]]
local OUT  = ROOT .. [[\translation\cardgame\vram]]
local SDIR = ROOT .. [[\BizHawk-master\output\PC Engine\State\]]
local function dump(dom, path)
  local size = memory.getmemorydomainsize(dom); local f = assert(io.open(path, "wb"))
  for a = 0, size - 1, 4096 do local n = math.min(4096, size - a); local b = memory.read_bytes_as_array(a, n, dom); local t = {}; for i = 1, n do t[i] = string.char(b[i]) end; f:write(table.concat(t)) end
  f:close()
end
pcall(function() client.speedmode(400) end)
for i = 1, 30 do emu.frameadvance() end
savestate.load(SDIR .. "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.PCEHawk.QuickSave3.State")
for i = 1, 10 do emu.frameadvance() end
for k = 1, 2 do
  for f = 1, 3 do pcall(joypad.set, {B2 = true}, 1); emu.frameadvance() end
  for f = 1, 120 do emu.frameadvance() end
  pcall(client.screenshot, OUT .. "/s8_try" .. k .. ".png")
  local tag = "s" .. (7 + k)
  dump("VRAM1", OUT .. "/" .. tag .. "_VRAM1.bin"); dump("VCEPalette", OUT .. "/" .. tag .. "_VCEPalette.bin"); dump("TurboCD RAM", OUT .. "/" .. tag .. "_TurboCD_RAM.bin")
end
if client.exitprogram then client.exitprogram() elseif client.exit then client.exit() end
