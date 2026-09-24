<#
.SYNOPSIS
    Starts the stem practice tool. Run activate.ps1 first (once).

.DESCRIPTION
    Starts uvicorn (FastAPI backend) in its own window so you can see
    backend logs/errors, waits for it to come up, then launches the
    Electron shell in the foreground. When you close the Electron window,
    this script stops the backend process too -- otherwise uvicorn would
    keep running invisibly and the next run.ps1 would fail to bind the port.
#>

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "ERROR: venv not found. Run .\activate.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".\frontend\dist\index.html")) {
    Write-Host "ERROR: frontend isn't built. Run .\activate.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Starting backend..." -ForegroundColor Cyan

$backendProcess = Start-Process powershell `
    -ArgumentList "-NoExit", "-Command", "& '.\.venv\Scripts\Activate.ps1'; cd backend; uvicorn main:app --host 127.0.0.1 --port 8000" `
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
