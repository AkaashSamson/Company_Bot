<#
.SYNOPSIS
    KnowLayer V3 Enterprise - Unified Application Setup & Runner

.DESCRIPTION
    Initializes environment, verifies dependencies, manages port conflicts,
    launches the FastAPI backend and Streamlit UI in coordinated windows,
    and performs automated readiness health checks.

.PARAMETER ApiPort
    Port number for the FastAPI backend (Default: 8000).

.PARAMETER StreamlitPort
    Port number for the Streamlit UI (Default: 8501).

.PARAMETER NoReload
    Disable hot-reloading on the FastAPI server (Hot reload is enabled by default for active development).

.PARAMETER InstallDeps
    Install/update dependencies from requirements.txt before launching.

.PARAMETER KillExisting
    Automatically terminate any running processes listening on ApiPort or StreamlitPort.

.PARAMETER Stop
    Stop all running KnowLayer services on the specified ports and exit without launching.

.PARAMETER NoBrowser
    Run Streamlit in headless mode without automatically launching a browser window.

.EXAMPLE
    .\setup.ps1
    Launches FastAPI and Streamlit with default settings and hot-reloading.

.EXAMPLE
    .\setup.ps1 -InstallDeps -KillExisting
    Updates requirements and ensures ports are clean before launching.

.EXAMPLE
    .\setup.ps1 -Stop
    Terminates running FastAPI and Streamlit servers on ports 8000 and 8501.
#>

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$StreamlitPort = 8501,
    [switch]$NoReload,
    [switch]$InstallDeps,
    [switch]$KillExisting,
    [switch]$Stop,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# --- Helper Functions ---
function Get-ProcessIdsOnPort([int]$Port) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop
        return ($connections.OwningProcess | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    }
    catch {
        # Fallback to netstat if Get-NetTCPConnection is unavailable
        $output = netstat -ano | Select-String ":$Port\s"
        $pids = @()
        foreach ($line in $output) {
            $parts = ($line.ToString().Trim() -split "\s+")
            if ($parts.Length -ge 5) {
                $pidVal = 0
                if ([int]::TryParse($parts[-1], [ref]$pidVal) -and $pidVal -gt 0) {
                    $pids += $pidVal
                }
            }
        }
        return ($pids | Select-Object -Unique)
    }
}

function Stop-PortProcesses([int]$Port, [string]$ServiceName) {
    $pids = Get-ProcessIdsOnPort $Port
    if ($pids -and $pids.Count -gt 0) {
        Write-Host "Stopping existing $ServiceName process(es) on port $Port (PIDs: $($pids -join ', '))..." -ForegroundColor Yellow
        foreach ($p in $pids) {
            try {
                Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            } catch {
                # Ignore errors if process already exited
            }
        }
        Start-Sleep -Milliseconds 500
    }
}

# --- Stop Mode ---
if ($Stop) {
    Write-Host "`n=== Stopping KnowLayer Services ===" -ForegroundColor Cyan
    Stop-PortProcesses $ApiPort "FastAPI Backend"
    Stop-PortProcesses $StreamlitPort "Streamlit UI"
    Write-Host "All KnowLayer services on ports $ApiPort and $StreamlitPort have been stopped.`n" -ForegroundColor Green
    exit 0
}

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host "  KnowLayer V3 Enterprise - Application Setup & Runner  " -ForegroundColor White
Write-Host "=======================================================`n" -ForegroundColor Cyan

# --- 1. Environment & Folder Verification ---
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "[INIT] Created .env configuration from .env.example" -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] No .env or .env.example found in project root" -ForegroundColor Yellow
    }
}

$InstanceDir = Join-Path $ProjectRoot "instance"
if (-not (Test-Path $InstanceDir)) {
    New-Item -ItemType Directory -Path $InstanceDir -Force | Out-Null
    Write-Host "[INIT] Created instance/ directory for SQLite database storage" -ForegroundColor Gray
}

$DataDir = Join-Path $ProjectRoot "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Write-Host "[INIT] Created data/ directory for cache files" -ForegroundColor Gray
}

# --- 2. Virtual Environment & Dependencies ---
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[CHECK] Virtual environment not found at .venv. Attempting automatic setup..." -ForegroundColor Yellow
    $SystemPython = Get-Command "python" -ErrorAction SilentlyContinue
    if (-not $SystemPython) {
        $SystemPython = Get-Command "py" -ErrorAction SilentlyContinue
    }
    if (-not $SystemPython) {
        throw "Python is not installed or not in PATH. Please install Python 3.11+ to run KnowLayer."
    }
    Write-Host "[INIT] Creating virtual environment at .venv..." -ForegroundColor Cyan
    & $SystemPython.Source -m venv (Join-Path $ProjectRoot ".venv")
    if (-not (Test-Path $VenvPython)) {
        throw "Failed to create virtual environment at .venv"
    }
    $InstallDeps = $true
}

if (-not $InstallDeps) {
    # Check if newly added dependencies (e.g. streamlit-cookies-controller) are installed
    $CheckDeps = & "$VenvPython" -c "import streamlit_cookies_controller" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[DEPS] Detected missing package(s). Installing dependencies from requirements.txt..." -ForegroundColor Yellow
        $InstallDeps = $true
    }
}

if ($InstallDeps) {
    Write-Host "[DEPS] Installing/Updating dependencies from requirements.txt..." -ForegroundColor Cyan
    & "$VenvPython" -m pip install --upgrade pip --quiet
    & "$VenvPython" -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    Write-Host "[DEPS] Dependencies up to date.`n" -ForegroundColor Green
}

# --- 3. Port Conflict Verification ---
$ApiPids = Get-ProcessIdsOnPort $ApiPort
$UiPids = Get-ProcessIdsOnPort $StreamlitPort

if ($ApiPids -or $UiPids) {
    if ($KillExisting) {
        if ($ApiPids) { Stop-PortProcesses $ApiPort "FastAPI Backend" }
        if ($UiPids) { Stop-PortProcesses $StreamlitPort "Streamlit UI" }
    } else {
        if ($ApiPids) {
            Write-Host "[ERROR] Port $ApiPort is already in use by PID(s): $($ApiPids -join ', ')." -ForegroundColor Red
        }
        if ($UiPids) {
            Write-Host "[ERROR] Port $StreamlitPort is already in use by PID(s): $($UiPids -join ', ')." -ForegroundColor Red
        }
        Write-Host "Tip: Run `".\setup.ps1 -KillExisting`" to automatically free these ports and restart." -ForegroundColor Yellow
        exit 1
    }
}

# --- 4. Launch FastAPI Backend ---
$ReloadArgs = if (-not $NoReload) { "--reload --reload-dir app" } else { "" }
$ApiCommand = "Set-Location '$ProjectRoot'; `$env:PYTHONPATH='$ProjectRoot'; `$Host.UI.RawUI.WindowTitle = 'KnowLayer API (Port $ApiPort)'; & '$VenvPython' -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort $ReloadArgs"

Write-Host "[LAUNCH] Starting FastAPI backend on http://127.0.0.1:$ApiPort..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $ApiCommand

# --- 5. Health Check Readiness Gate ---
Write-Host "[HEALTH] Waiting for FastAPI backend to become ready..." -NoNewline -ForegroundColor Gray
$HealthUrl = "http://127.0.0.1:$ApiPort/health"
$MaxRetries = 30
$IsReady = $false

for ($i = 1; $i -le $MaxRetries; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($response -and $response.status -eq "ok") {
            $IsReady = $true
            break
        }
    } catch {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
}

if ($IsReady) {
    Write-Host " [ONLINE]" -ForegroundColor Green
} else {
    Write-Host " [TIMEOUT]" -ForegroundColor Yellow
    Write-Host "[WARN] FastAPI health check did not respond within $MaxRetries seconds. Proceeding to launch UI..." -ForegroundColor Yellow
}

# --- 6. Launch Streamlit UI ---
$HeadlessArg = if ($NoBrowser) { "--server.headless true" } else { "--server.headless false" }
$UiCommand = "Set-Location '$ProjectRoot'; `$env:PYTHONPATH='$ProjectRoot'; `$env:STREAMLIT_API_BASE_URL='http://127.0.0.1:$ApiPort'; `$Host.UI.RawUI.WindowTitle = 'KnowLayer Streamlit UI (Port $StreamlitPort)'; & '$VenvPython' -m streamlit run streamlit_app/app.py --server.port $StreamlitPort --server.address 127.0.0.1 $HeadlessArg"

Write-Host "[LAUNCH] Starting Streamlit frontend on http://127.0.0.1:$StreamlitPort..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $UiCommand

# --- 7. Application Ready Summary ---
Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host "         KnowLayer Services Successfully Launched      " -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "  * FastAPI Backend:   http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  * Interactive Docs:  http://127.0.0.1:$ApiPort/docs" -ForegroundColor White
Write-Host "  * Streamlit UI:      http://127.0.0.1:$StreamlitPort" -ForegroundColor White
Write-Host "  * Default Admin:     Username: 'admin' (Password in .env)" -ForegroundColor DarkGray
Write-Host "-------------------------------------------------------" -ForegroundColor Gray
Write-Host "  Commands:" -ForegroundColor Gray
Write-Host "    Stop services:     .\setup.ps1 -Stop" -ForegroundColor Cyan
Write-Host "    Restart & kill:    .\setup.ps1 -KillExisting" -ForegroundColor Cyan
Write-Host "    Update packages:   .\setup.ps1 -InstallDeps" -ForegroundColor Cyan
Write-Host "=======================================================`n" -ForegroundColor Green
