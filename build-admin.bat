@echo off
rem Build an exe that requests administrator rights at startup.
rem Needed to read CPU time of services / other users (e.g. EdmServerV6.exe).
setlocal
cd /d "%~dp0"
where pwsh >nul 2>&1
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" -Admin
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" -Admin
)
echo.
pause
