# Mednafen 단독 실행 스모크 (2026-10-11): 지정 모듈(pce / pce_fast)로 cue + 시스템 카드 부팅 → Run(Enter) → 새 게임 → I(H) 반복 → F9 스냅샷.
# mednafen.cfg 는 실행 전에 백업하고 끝나면 되돌린다(Mednafen 은 종료 때 명령줄 설정까지 cfg 에 저장).
param([string]$Module = "pce", [string]$Cue, [string]$Card, [string]$Tag = "smoke", [int]$Seconds = 150, [int]$RunSec = 30)   # RunSec = Run(Enter) 누르는 시간(pce_fast 는 타이틀이 늦게 떠 더 길게)
$ErrorActionPreference = "Stop"
$MD = "G:\Downloads\mednafen-1.32.1-win64"
$SNAP = "$MD\snaps"
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class MW { public delegate bool EnumProc(IntPtr h, IntPtr p);
[DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
[DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool f);
[DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int c);
[DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
[DllImport("user32.dll")] static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
[DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint f, UIntPtr e);
public struct RECT { public int L,T,R,B; } public struct POINT { public int X,Y; }
public static IntPtr Find(uint pid) { IntPtr found = IntPtr.Zero; EnumWindows((h,p)=>{ if(!IsWindowVisible(h)) return true; uint q; GetWindowThreadProcessId(h, out q); if(q==pid){ found=h; return false;} return true; }, IntPtr.Zero); return found; }
public static void Focus(IntPtr h) { keybd_event(0x12,0,0,UIntPtr.Zero); keybd_event(0x12,0,2,UIntPtr.Zero); var fg=GetForegroundWindow(); uint t1=GetWindowThreadProcessId(fg,IntPtr.Zero); uint t2=GetCurrentThreadId(); AttachThreadInput(t2,t1,true); ShowWindow(h,9); SetForegroundWindow(h); AttachThreadInput(t2,t1,false);
  RECT r; GetWindowRect(h, out r); POINT old; GetCursorPos(out old); SetCursorPos((r.L+r.R)/2,(r.T+r.B)/2); System.Threading.Thread.Sleep(50);
  mouse_event(2,0,0,0,UIntPtr.Zero); mouse_event(4,0,0,0,UIntPtr.Zero); System.Threading.Thread.Sleep(50); SetCursorPos(old.X,old.Y); }
public static void Key(byte vk, byte scan, int holdMs) { keybd_event(vk, scan, 0, UIntPtr.Zero); System.Threading.Thread.Sleep(holdMs); keybd_event(vk, scan, 2, UIntPtr.Zero); } }
"@
Copy-Item "$MD\mednafen.cfg" "$MD\mednafen.cfg.bak_smoke" -Force
$before = @(Get-ChildItem $SNAP -Filter *.png -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
$margs = @("-video.fs", "0", "-force_module", $Module, "-$Module.cdbios", "`"$Card`"")
if ($Module -eq "pce_fast") {
  $margs += @("-pce_fast.input.port1.gamepad.run", "`"keyboard 0x0 40`"", "-pce_fast.input.port1.gamepad.i", "`"keyboard 0x0 11`"", "-pce_fast.input.port1.gamepad.ii", "`"keyboard 0x0 13`"")
}
$margs += "`"$Cue`""
$p = Start-Process -FilePath "$MD\mednafen.exe" -ArgumentList $margs -WorkingDirectory $MD -PassThru
try {
  $h = [IntPtr]::Zero; $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($h -eq [IntPtr]::Zero -and $sw.ElapsedMilliseconds -lt 30000 -and -not $p.HasExited) { $h = [MW]::Find([uint32]$p.Id); [Threading.Thread]::Sleep(200) }
  if ($p.HasExited) { "mednafen exited early (code $($p.ExitCode))"; return }
  [Threading.Thread]::Sleep(2000); [MW]::Focus($h)
  $t0 = Get-Date
  $snapAt = @(6, 20, 40, 60, 80, 100, 120, 140)
  $si = 0
  while (((Get-Date) - $t0).TotalSeconds -lt $Seconds -and -not $p.HasExited) {
    $el = ((Get-Date) - $t0).TotalSeconds
    if ([MW]::GetForegroundWindow() -ne $h) { [MW]::Focus($h) }
    if ($el -lt $RunSec) { [MW]::Key(0x0D, 0x1C, 120) } else { [MW]::Key(0x4C, 0x26, 120) }   # 30초 전 Run(Enter), 이후 I(L — 2026-10-12 키 변경 I=L, II=K)
    if ($si -lt $snapAt.Count -and $el -ge $snapAt[$si]) { [MW]::Key(0x78, 0x43, 80); $si++ }   # F9 스냅샷
    [Threading.Thread]::Sleep(1800)
  }
} finally {
  if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
  Start-Sleep -Milliseconds 800
  Copy-Item "$MD\mednafen.cfg.bak_smoke" "$MD\mednafen.cfg" -Force
}
$after = @(Get-ChildItem $SNAP -Filter *.png | Where-Object { $before -notcontains $_.Name } | Sort-Object LastWriteTime)
"new snaps: " + ($after | ForEach-Object { $_.Name }) -join ", "
