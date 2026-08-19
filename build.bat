@echo off
rem プロセス CPU モニターを exe にビルドします（ダブルクリックで実行可）。
rem 管理者権限を要求する exe が必要な場合は build-admin.bat を使ってください。
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
echo.
pause
