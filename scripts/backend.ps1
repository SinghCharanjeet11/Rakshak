<#
.SYNOPSIS
  Starts the Rakshak backend on http://localhost:8000

.DESCRIPTION
  Handles the four things that actually go wrong when starting this by hand:

    1. Wrong directory  — resolves paths from the script's own location, so it works
                          from any working directory.
    2. Wrong python     — always uses .venv\Scripts\python.exe. A bare `python` picks up
                          the system interpreter, which has none of the dependencies.
    3. No venv          — creates it and installs on first run instead of erroring.
    4. Port in use      — reports the PID holding :8000 rather than failing with a
                          confusing "address already in use".

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\backend.ps1
  powershell -ExecutionPolicy Bypass -File scripts\backend.ps1 -Port 8001 -NoReload
#>
param(
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python  = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $backend)) {
    Write-Error "No backend/ directory at $backend - is this the right repo?"
}

# --- venv -------------------------------------------------------------------
if (-not (Test-Path $python)) {
    Write-Host "No virtualenv found. Creating one (first run only)..." -ForegroundColor Yellow
    python -m venv (Join-Path $backend ".venv")
    if (-not (Test-Path $python)) {
        Write-Error "Could not create the virtualenv. Is Python 3.11+ on PATH? Try: python --version"
    }
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    & $python -m pip install --quiet --upgrade pip
    & $python -m pip install --quiet -e "$backend[dev]"
    Write-Host "Dependencies installed." -ForegroundColor Green
}

# --- port -------------------------------------------------------------------
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $holder = $busy[0].OwningProcess
    $name = (Get-Process -Id $holder -ErrorAction SilentlyContinue).ProcessName
    Write-Host "Port $Port is already in use by PID $holder ($name)." -ForegroundColor Yellow
    Write-Host "  If that is an old Rakshak backend, stop it with:  Stop-Process -Id $holder -Force"
    Write-Host "  Or start on another port:                         .\scripts\backend.ps1 -Port 8001"
    exit 1
}

# --- go ---------------------------------------------------------------------
Write-Host ""
Write-Host "  Rakshak backend  ->  http://localhost:$Port" -ForegroundColor Green
Write-Host "  health              http://localhost:$Port/api/v1/health"
Write-Host "  API docs            http://localhost:$Port/docs"
Write-Host "  stop                Ctrl+C"
Write-Host ""

Set-Location $backend
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--port", $Port)
if (-not $NoReload) { $uvicornArgs += "--reload" }
& $python @uvicornArgs
