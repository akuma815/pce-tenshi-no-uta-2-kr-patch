@echo off
rem Copy in-game save: original game (PCEHawk capture) -> b8 (TurboNyma).
rem Close ALL EmuHawk windows BEFORE running (SaveRAM is written on exit).
set "DIR=%~dp0..\BizHawk-master\output\PC Engine\SaveRAM"
set "SRC=%DIR%\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.SaveRAM"
set "DST=%DIR%\Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b8.SaveRAM"
if not exist "%SRC%" ( echo [FAIL] original SaveRAM not found & pause & exit /b 1 )
copy /Y "%DST%" "%DST%.prev" >nul 2>&1
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 ( echo [FAIL] copy error & pause & exit /b 1 )
echo [OK] capture(original) save -^> b8 SaveRAM
pause
