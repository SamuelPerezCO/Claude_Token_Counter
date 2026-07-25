@echo off
REM Double-click this file to build claude-meter.exe.
REM
REM Why this exists: PowerShell's execution policy blocks .ps1 files that came
REM from the internet, so someone who downloaded this repo as a ZIP would hit
REM "running scripts is disabled on this system" when running build_exe.ps1
REM directly. Batch files are not subject to that policy, so this wrapper works
REM on a stock Windows machine with nothing configured.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"

echo.
echo Press any key to close this window.
pause >nul
