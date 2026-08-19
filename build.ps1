<#
.SYNOPSIS
    プロセス CPU モニターを単一 exe (dist\ProcCpuMonitor.exe) にビルドします。

.DESCRIPTION
    Python 3.9 以降が必要です（https://www.python.org/downloads/windows/ ）。
    PyInstaller が未インストールなら自動で導入します。

.PARAMETER Admin
    起動時に管理者権限を要求する exe (ProcCpuMonitor-Admin.exe) を作ります。
    サービスや別ユーザーとして動くプロセス（EdmServerV6.exe など）の
    CPU 時間を読むにはこちらが必要です。

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Admin
#>
[CmdletBinding()]
param(
    [switch]$Admin,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# --- Python を探す -----------------------------------------------------
$pythonExe = $null
$pythonPrefix = @()
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
        $pythonExe = $candidate[0]
        $pythonPrefix = @($candidate | Select-Object -Skip 1)
        break
    }
}
if (-not $pythonExe) {
    throw "Python が見つかりません。https://www.python.org/downloads/windows/ からインストールし、[Add python.exe to PATH] を有効にしてください。"
}

Write-Host "使用する Python: $pythonExe $pythonPrefix" -ForegroundColor Cyan
& $pythonExe @($pythonPrefix + @("--version"))
if ($LASTEXITCODE -ne 0) { throw "Python の実行に失敗しました。" }

# --- PyInstaller ------------------------------------------------------
if (-not $SkipInstall) {
    Write-Host "PyInstaller を確認しています..." -ForegroundColor Cyan
    & $pythonExe @($pythonPrefix + @("-m", "pip", "install", "--upgrade", "--disable-pip-version-check", "pyinstaller"))
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller のインストールに失敗しました。" }
}

# --- ビルド -----------------------------------------------------------
$name = if ($Admin) { "ProcCpuMonitor-Admin" } else { "ProcCpuMonitor" }
$pyArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--onefile", "--windowed",
    "--name", $name,
    "--paths", "src",
    "--exclude-module", "numpy",
    "--exclude-module", "matplotlib",
    "--exclude-module", "PIL",
    "--exclude-module", "unittest",
    "--exclude-module", "pydoc",
    "main.py"
)
if ($Admin) { $pyArgs += "--uac-admin" }

Write-Host "ビルド中..." -ForegroundColor Cyan
& $pythonExe @($pythonPrefix + $pyArgs)
if ($LASTEXITCODE -ne 0) { throw "ビルドに失敗しました。" }

$output = Join-Path $PSScriptRoot "dist\$name.exe"
if (-not (Test-Path $output)) { throw "exe が生成されませんでした: $output" }

$size = [math]::Round((Get-Item $output).Length / 1MB, 1)
Write-Host ""
Write-Host "完成: $output ($size MB)" -ForegroundColor Green
