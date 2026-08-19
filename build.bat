@echo off
rem Build the process CPU monitor into a single exe (double-click to run).
rem Use build-admin.bat if you need the exe to request administrator rights.
setlocal
cd /d "%~dp0"
where pwsh >nul 2>&1
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
)
echo.
pause
