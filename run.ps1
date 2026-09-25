<#
.SYNOPSIS
    Starts the stem practice tool. Run activate.ps1 first (once).

.DESCRIPTION
    Starts uvicorn (FastAPI backend) in its own window so you can see
    backend logs/errors, waits for it to come up, then launches the
    Electron shell in the foreground. When you close the Electron window,
    this script stops the backend process too -- otherwise uvicorn would
    keep running invisibly and the next run.ps1 would fail to bind the port.

    Auto-rebuild: before launching, this script compares the newest
    file under frontend/src/ (and vite.config.js / package.json) against
    frontend/dist/index.html. If anything is newer the frontend is
    rebuilt automatically -- no manual `npm run build` needed.
    Uses `cmd /c npm run build` to sidestep PowerShell execution-policy
    restrictions on npm.
#>

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "ERROR: venv not found. Run .\activate.ps1 first." -ForegroundColor Red
    exit 1
}

# --- Frontend staleness check + auto-rebuild ------------------------------------
#
# Compare the newest mtime across frontend/src/**/* plus vite.config.js and
# package.json against frontend/dist/index.html. Rebuild whenever src is newer
# or dist doesn't exist yet.

$distIndex = ".\frontend\dist\index.html"

if (-not (Test-Path $distIndex)) {
    Write-Host "No dist found -- building frontend for the first time..." -ForegroundColor Cyan
    Push-Location frontend
    cmd /c npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: frontend build failed. Check the output above." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
} else {
    $distTime = (Get-Item $distIndex).LastWriteTimeUtc

    # Gather all source files that should trigger a rebuild when changed
    $srcFiles = @(
        Get-ChildItem -Path ".\frontend\src" -Recurse -File
        Get-Item ".\frontend\vite.config.js" -ErrorAction SilentlyContinue
        Get-Item ".\frontend\package.json"   -ErrorAction SilentlyContinue
    ) | Where-Object { $_ -ne $null }

    $newestSrc = ($srcFiles | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc

    if ($newestSrc -gt $distTime) {
        Write-Host "Source files changed since last build -- rebuilding frontend..." -ForegroundColor Cyan
        Push-Location frontend
        cmd /c npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: frontend build failed. Check the output above." -ForegroundColor Red
            Pop-Location
            exit 1
        }
        Pop-Location
        Write-Host "Frontend rebuilt successfully." -ForegroundColor Green
    } else {
        Write-Host "Frontend is up to date (no rebuild needed)." -ForegroundColor Green
    }
}

if (-not (Test-Path $distIndex)) {
    Write-Host "ERROR: dist/index.html still missing after build attempt." -ForegroundColor Red
    exit 1
}

Write-Host "Starting backend..." -ForegroundColor Cyan

$backendProcess = Start-Process powershell `
    -ArgumentList "-NoExit", "-Command", "& '.\venv\Scripts\Activate.ps1'; cd backend; uvicorn main:app --host 127.0.0.1 --port 8000" `
    -PassThru

# Poll the backend instead of a fixed sleep -- startup time varies a lot
# depending on whether torch/demucs are already warm in disk cache.
$maxWaitSeconds = 30
$waited = 0
$backendUp = $false

Write-Host "Waiting for backend to come up..."
while ($waited -lt $maxWaitSeconds) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/songs" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $backendUp = $true
            break
        }
    } catch {
        # Not up yet -- expected during startup, keep polling.
    }
    Start-Sleep -Seconds 1
    $waited++
}

if (-not $backendUp) {
    Write-Host "WARNING: backend didn't respond within $maxWaitSeconds seconds." -ForegroundColor Yellow
    Write-Host "Launching Electron anyway -- it has its own retry logic and will show" -ForegroundColor Yellow
    Write-Host "an error if the backend truly failed. Check the backend window for errors." -ForegroundColor Yellow
} else {
    Write-Host "Backend is up." -ForegroundColor Green
}

Write-Host "Starting Electron shell..." -ForegroundColor Cyan
Push-Location electron
try {
    cmd /c npm start
} finally {
    Pop-Location
    Write-Host "Electron closed. Stopping backend..." -ForegroundColor Cyan
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
