# Builds dist\claude-meter.exe -- a single self-contained executable.
#
#   .\build_exe.ps1
#
# Building from the project venv (rather than a global Python) keeps PyInstaller
# from sweeping unrelated site-packages into the bundle.
#
# Note: we deliberately do NOT set $ErrorActionPreference = "Stop". In Windows
# PowerShell 5.1 anything a native .exe writes to stderr -- including harmless
# pip notices -- surfaces as a NativeCommandError and would abort the build.
# We gate on $LASTEXITCODE instead, which is what actually indicates failure.

Set-Location $PSScriptRoot

function Invoke-Step {
    param([string]$Description, [scriptblock]$Action)
    Write-Host $Description -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Description (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

$python = ".\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Invoke-Step "Creating virtual environment..." { python -m venv venv }
}

# A running instance holds a lock on the .exe and PyInstaller fails with
# "Access is denied" when it tries to overwrite it. Note the onefile bootloader
# spawns a child, so an earlier run can outlive the console you started it from.
$running = Get-Process -Name "claude-meter" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "Stopping $($running.Count) running claude-meter instance(s)..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Invoke-Step "Installing build dependencies..." {
    & $python -m pip install --quiet --upgrade -r requirements.txt
}

Invoke-Step "Building executable..." {
    & $python -m PyInstaller `
        --noconfirm `
        --onefile `
        --console `
        --name claude-meter `
        --add-data "claude_meter/static;claude_meter/static" `
        --hidden-import qrcode `
        run.py
}

$exe = Join-Path $PSScriptRoot "dist\claude-meter.exe"
if (-not (Test-Path $exe)) {
    Write-Host "PyInstaller reported success but $exe is missing." -ForegroundColor Red
    exit 1
}

$size = "{0:N1} MB" -f ((Get-Item $exe).Length / 1MB)
Write-Host ""
Write-Host "Built $exe ($size)" -ForegroundColor Green
Write-Host "Double-click it, or run: .\dist\claude-meter.exe --open"
