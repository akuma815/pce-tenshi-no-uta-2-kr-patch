# 자동 Lua 프로브 실행기 (2026-10-11): Lua 콘솔이 뜨면서 EmuHawk 메인 창이 비활성화되어 패드 입력이 안 먹는 문제 대응.
# 순서: 신호 파일 삭제 → EmuHawk 실행 → 메인 창·Lua 콘솔이 모두 뜰 때까지 대기 → 메인 창 선택 → 신호 파일 생성(Lua 가 일시정지 해제) → 종료 대기.
# Lua 쪽은 시작 시 client.pause() 후 신호 파일(FOCUS_FLAG)이 생길 때까지 emu.yield() 로 기다려야 한다.
param([string]$Cue, [string]$Config, [string]$Lua, [string]$TitlePart, [int]$TimeoutSec = 300, [string[]]$Extra = @())   # $Extra = EmuHawk 추가 인자(예: --dump-type=wave)
$ErrorActionPreference = "Stop"
$R = Split-Path -Parent $PSScriptRoot
$Flag = "C:\Users\akuma\AppData\Local\Temp\claude\g--Downloads-Korean-Traslate-Project\4810c544-ca01-4c35-9ec3-049a276c76c9\scratchpad\focus.flag"
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class FocusWin { public delegate bool EnumProc(IntPtr h, IntPtr p);
[DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
[DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
[DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
[DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool f);
[DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int c);
[DllImport("user32.dll")] static extern void keybd_event(byte k, byte s, uint f, UIntPtr e);
[DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
[DllImport("user32.dll")] static extern void mouse_event(uint f, int x, int y, uint d, UIntPtr e);
public struct RECT { public int L,T,R,B; } public struct POINT { public int X,Y; }
public static void Click(IntPtr h) { RECT r; GetWindowRect(h, out r); POINT old; GetCursorPos(out old);
  SetCursorPos((r.L + r.R) / 2, (r.T + r.B) / 2 + 20); System.Threading.Thread.Sleep(50);
  mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); System.Threading.Thread.Sleep(50);
  SetCursorPos(old.X, old.Y); }
[DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
public static IntPtr Find(string part, uint pid) { IntPtr found = IntPtr.Zero; EnumWindows((h,p)=>{ if(!IsWindowVisible(h)) return true; uint q; GetWindowThreadProcessId(h, out q); if(q!=pid) return true; var sb=new StringBuilder(512); GetWindowText(h,sb,512); if(sb.ToString().Contains(part)){ found=h; return false;} return true; }, IntPtr.Zero); return found; }
public static bool Focus(IntPtr h) { keybd_event(0x12,0,0,UIntPtr.Zero); keybd_event(0x12,0,2,UIntPtr.Zero); var fg=GetForegroundWindow(); uint t1=GetWindowThreadProcessId(fg,IntPtr.Zero); uint t2=GetCurrentThreadId(); AttachThreadInput(t2,t1,true); ShowWindow(h,9); bool ok=SetForegroundWindow(h); AttachThreadInput(t2,t1,false); return ok; } }
"@
if (Test-Path $Flag) { Remove-Item $Flag -Force }
$p = Start-Process -FilePath "$R\BizHawk-master\output\EmuHawk.exe" -ArgumentList (@("`"$Cue`"", "--config=`"$Config`"", "--lua=`"$Lua`"") + $Extra) -PassThru
$sw = [Diagnostics.Stopwatch]::StartNew()
$main = [IntPtr]::Zero; $luaw = [IntPtr]::Zero
while (($main -eq [IntPtr]::Zero -or $luaw -eq [IntPtr]::Zero) -and $sw.ElapsedMilliseconds -lt 60000) {
  $main = [FocusWin]::Find($TitlePart, [uint32]$p.Id); $luaw = [FocusWin]::Find("Lua Console", [uint32]$p.Id)   # 사용자 창(같은 제목)과 구분: 내가 띄운 프로세스의 창만
  [Threading.Thread]::Sleep(200)
}
[Threading.Thread]::Sleep(1500)                       # Lua 콘솔이 포커스를 가져간 뒤
$ok = $false
for ($i = 0; $i -lt 10 -and -not $ok; $i++) {
  [void][FocusWin]::Focus($main); [Threading.Thread]::Sleep(300)
  $ok = ([FocusWin]::GetForegroundWindow() -eq $main)
}
[FocusWin]::Click($main); [Threading.Thread]::Sleep(300)   # 활성화만으로는 입력이 안 먹는다 — 창 안을 한 번 클릭해야 함(사용자 실측)
"main=$main lua=$luaw focused=$ok clicked"
New-Item -ItemType File -Path $Flag -Force | Out-Null
if (-not $p.WaitForExit($TimeoutSec * 1000)) { Stop-Process -Id $p.Id -Force; "timeout" } else { "exited" }
