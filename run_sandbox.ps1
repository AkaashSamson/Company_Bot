<#
.SYNOPSIS
    Launch the KnowLayer Developer Sandbox.

.DESCRIPTION
    Runs the Streamlit Developer Sandbox on port 8502.
    Does not require Docker or the FastAPI backend to be running.

.EXAMPLE
    .\run_sandbox.ps1
#>

[CmdletBinding()]
param(
    [int]$Port = 8502
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# Locate virtual environment Python
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

# Free port if already listening
try {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    $pids = $connections.OwningProcess | Where-Object { $_ -gt 0 } | Select-Object -Unique
    if ($pids) {
        Write-Host "Freeing occupied port $Port (PID: $($pids -join ', '))..." -ForegroundColor Yellow
        foreach ($p in $pids) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 500
    }
} catch {}

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host "   KnowLayer Developer Sandbox & Observability Suite   " -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  * Mode:     Standalone Local Dashboard" -ForegroundColor Gray
Write-Host "  * URL:      http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  * Python:   $VenvPython" -ForegroundColor Gray
Write-Host "=======================================================`n" -ForegroundColor Cyan

$env:PYTHONPATH = $ProjectRoot
& "$VenvPython" -m streamlit run sandbox/sandbox_app.py --server.port $Port --server.address 127.0.0.1
