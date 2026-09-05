<#
.SYNOPSIS
  Starts the Rakshak frontend on http://localhost:3000

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\frontend.ps1          # production build
  powershell -ExecutionPolicy Bypass -File scripts\frontend.ps1 -Dev     # hot reload
#>
param(
    [int]$Port = 3000,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$root     = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"

if (-not (Test-Path $frontend)) { Write-Error "No frontend/ directory at $frontend" }
Set-Location $frontend

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing dependencies (first run only)..." -ForegroundColor Yellow
    npm install --no-audit --no-fund
}

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $holder = $busy[0].OwningProcess
    Write-Host "Port $Port is in use by PID $holder. Stop it with: Stop-Process -Id $holder -Force" -ForegroundColor Yellow
    exit 1
}

$env:PORT = $Port

if ($Dev) {
    Write-Host ""
    Write-Host "  Rakshak frontend (dev) ->  http://localhost:$Port" -ForegroundColor Green
    Write-Host ""
    npm run dev
} else {
    # `next start` serves .next/ — if it is missing or stale the app 500s in ways that
    # look like application bugs, so always build first.
    #
    # The retry exists because a half-written .next leaves every later build failing on the
    # wreckage rather than on the real error. That was originally an OneDrive problem — it
    # dehydrates files into cloud placeholders (reparse points), Next's cleanup step calls
    # readlink on them and dies with EINVAL. The repo moved out of OneDrive on 2026-09-04,
    # but an interrupted build can still strand a stale .next, and nuking it and retrying
    # once recovers that too.
    Write-Host "Building..." -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Build failed. Clearing .next and retrying once..." -ForegroundColor Yellow
        cmd /c "rmdir /s /q .next" 2>$null
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Build failed twice, so a stale .next is not the cause - read the actual error above. ('readlink' or EINVAL means the repo sits on a cloud-synced folder; it was moved to c:\dev\Rakshak on 2026-09-04 to avoid exactly that, so check it has not been moved back.)"
        }
    }
    Write-Host ""
    Write-Host "  Rakshak frontend  ->  http://localhost:$Port" -ForegroundColor Green
    Write-Host "  The backend must also be running on :8000 for data to load."
    Write-Host ""
    npm run start
}
