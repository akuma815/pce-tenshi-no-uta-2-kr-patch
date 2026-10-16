<#
  Step 28 — Work RAM 생존성 트레이스 실행 스크립트
  H:\BizHawk (PCEHawk 코어, Super System Card 3.0(J) 펌웨어 구비)로 트레이서를 붙여 게임을 띄운다.

  사용:
    powershell -ExecutionPolicy Bypass -File tools\run_liveness_trace.ps1
    powershell -ExecutionPolicy Bypass -File tools\run_liveness_trace.ps1 -Patched   # 패치본으로 실행
    powershell -ExecutionPolicy Bypass -File tools\run_liveness_trace.ps1 -KeepTsv    # 기존 TSV 유지

  실행 후: 타이틀→뉴게임→마을→대사 여러 개→메뉴→전투→씬전환 20회 이상 플레이한 뒤
           EmuHawk를 정상 종료(창 닫기)하면 TSV가 완성된다(15초마다 중간 저장도 됨).
           그 다음  python tools\analyze_work_ram_liveness.py  로 판정.
#>
[CmdletBinding()]
param(
    [string]$EmuHawk = "H:\BizHawk\EmuHawk.exe",
    [switch]$Patched,   # 지정 시 패치본 cue 사용(기본은 원본 — 생존성은 원본으로 재는 게 정석)
    [switch]$KeepTsv,   # 지정 시 기존 TSV를 지우지 않음
    [switch]$Fast,      # 고속 프레임-diff write 추적(전역). 1차 스크리닝용.
    [switch]$Scene      # 씬별(CD_READ 윈도우) 스크래치 추적. Step 29 핵심.
)

$ErrorActionPreference = "Stop"
$Game = Split-Path -Parent $PSScriptRoot   # 게임 루트(= tools의 상위)
$Lua  = if ($Scene) {
    Join-Path $PSScriptRoot "trace_scene_scratch.lua"
} elseif ($Fast) {
    Join-Path $PSScriptRoot "trace_work_ram_writes_fast.lua"
} else {
    Join-Path $PSScriptRoot "trace_work_ram_liveness.lua"
}
$Cue  = if ($Patched) {
    Join-Path $Game "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_patched.cue"
} else {
    Join-Path $Game "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
}
$RawTsv  = if ($Scene) { Join-Path $Game "translation\scene_scratch.tsv" }
           elseif ($Fast) { Join-Path $Game "translation\work_ram_writes_fast.tsv" }
           else { Join-Path $Game "translation\work_ram_liveness.tsv" }
$RunTsv  = if ($Scene) { $RawTsv } else { Join-Path $Game "translation\work_ram_untouched_runs.tsv" }

function Fail($m) { Write-Host "[오류] $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $EmuHawk)) { Fail "EmuHawk를 찾을 수 없음: $EmuHawk" }
if (-not (Test-Path $Lua))     { Fail "트레이서 Lua 없음: $Lua" }
if (-not (Test-Path $Cue))     { Fail "cue 파일 없음: $Cue" }

# PCEHawk 코어 확인(트레이서는 PCEHawk에서만 동작; TurboNyma는 조용히 실패)
$cfg = Join-Path (Split-Path -Parent $EmuHawk) "config.ini"
if (Test-Path $cfg) {
    $pcecd = (Select-String -Path $cfg -Pattern '"PCECD"\s*:\s*"([^"]+)"' | Select-Object -First 1)
    if ($pcecd -and $pcecd.Matches[0].Groups[1].Value -ne "PCEHawk") {
        Write-Host "[경고] 이 BizHawk의 PCE-CD 코어가 '$($pcecd.Matches[0].Groups[1].Value)' 입니다." -ForegroundColor Yellow
        Write-Host "       트레이서는 PCEHawk에서만 동작합니다. Config→Cores→PCE-CD=PCEHawk 로 바꾸세요." -ForegroundColor Yellow
    } else {
        Write-Host "[확인] PCE-CD 코어 = PCEHawk" -ForegroundColor Green
    }
}

if (-not $KeepTsv) {
    Remove-Item $RawTsv, $RunTsv -ErrorAction SilentlyContinue
    Write-Host "[정리] 기존 TSV 삭제"
}

Write-Host ""
Write-Host "EmuHawk 실행: $EmuHawk  $(if($Fast){'[고속 write-diff 모드]'}else{'[정밀 콜백 모드]'})"
Write-Host "  코어 트레이서: $Lua"
Write-Host "  대상 이미지 : $Cue  $(if($Patched){'(패치본)'}else{'(원본)'})"
Write-Host ""
Write-Host ">> 창이 뜨면 게임을 대표 장면들로 플레이(씬전환 20회 이상)한 뒤 창을 닫으세요." -ForegroundColor Cyan
Write-Host ">> 종료 후:  python tools\analyze_work_ram_liveness.py" -ForegroundColor Cyan
Write-Host ""

# 경로에 공백이 있으므로 각 인자를 리터럴 따옴표로 감싸 전달(그러지 않으면 EmuHawk가 공백에서 인자를 쪼갬)
$argList = @(
    ('"--lua={0}"' -f $Lua),
    ('"{0}"' -f $Cue)
)
Start-Process -FilePath $EmuHawk -ArgumentList $argList -Wait

Write-Host ""
if (Test-Path $RunTsv) {
    Write-Host "[완료] TSV 생성됨:" -ForegroundColor Green
    Get-Item $RawTsv, $RunTsv | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
    Write-Host "이제 실행:  python tools\analyze_work_ram_liveness.py"
} else {
    Write-Host "[주의] TSV가 없습니다. 게임이 실제로 구동/에뮬레이션 되었는지, 코어가 PCEHawk인지 확인하세요." -ForegroundColor Yellow
}
