@echo off
rem 起動時に管理者権限を要求する exe をビルドします。
rem サービス／別ユーザーとして動くプロセス（EdmServerV6.exe など）を計測する場合はこちら。
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" -Admin
echo.
pause
