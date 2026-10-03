<#
.SYNOPSIS
    Start mwtn. Run .\activate.ps1 first (once, on first setup).

.DESCRIPTION
    1. Checks the venv exists and Activate.ps1 is present.
    2. Checks frontend/static/index.html is present.
    3. Starts uvicorn (FastAPI backend) in a named background window.
    4. Polls http://127.0.0.1:8000/api/songs until it responds (up to 30 s).
    5. Opens the app in Electron (if installed) or prints the browser URL
       and opens it in the default browser.
    6. Kills the backend process cleanly when Electron closes (or on Ctrl+C).
#>

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== mwtn ===" -ForegroundColor Cyan
Write-Host ""

# ── Pre-flight: venv ──────────────────────────────────────────────────────────

$venvActivate = ".\venv\Scripts\Activate.ps1"
$venvPython   = ".\venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: venv not found or incomplete." -ForegroundColor Red
    Write-Host "       Run .\activate.ps1 first to set it up." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $venvActivate)) {
    Write-Host "ERROR: venv\Scripts\Activate.ps1 is missing." -ForegroundColor Red
    Write-Host "       Run .\activate.ps1 to repair the venv." -ForegroundColor Yellow
    exit 1
}

# ── Pre-flight: frontend ──────────────────────────────────────────────────────

if (-not (Test-Path ".\frontend\static\index.html")) {
    Write-Host "ERROR: frontend\static\index.html not found." -ForegroundColor Red
    Write-Host "       Make sure the project files are intact." -ForegroundColor Yellow
    exit 1
}

Write-Host "Frontend : OK" -ForegroundColor Green

# ── Start backend ─────────────────────────────────────────────────────────────

Write-Host "Starting mwtn backend…" -ForegroundColor Cyan

$activatePath = (Resolve-Path $venvActivate).Path
$backendPath  = (Resolve-Path ".\backend").Path

$backendCmd = `
  "`$host.UI.RawUI.WindowTitle = 'mwtn backend'; " + `
  "& '$activatePath'; " + `
  "Set-Location '$backendPath'; " + `
  "uvicorn main:app --host 127.0.0.1 --port 8000"

$backendProc = Start-Process powershell `
    -ArgumentList "-NoExit", "-Command", $backendCmd `
    -PassThru

# ── Poll until backend is up ──────────────────────────────────────────────────

$maxWait = 30
$waited  = 0
$up      = $false

Write-Host "Waiting for backend" -NoNewline
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    Write-Host "." -NoNewline
    try {
        $r = Invoke-WebRequest `
            -Uri "http://127.0.0.1:8000/api/songs" `
            -UseBasicParsing `
            -TimeoutSec 2 `
            -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch { }
}

Write-Host ""

if ($up) {
    Write-Host "Backend  : up at http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Host "WARNING  : backend didn't respond in ${maxWait}s." -ForegroundColor Yellow
    Write-Host "           Check the 'mwtn backend' window for errors." -ForegroundColor Yellow
}

# ── Launch app ────────────────────────────────────────────────────────────────

$electronReady = (Test-Path ".\electron\node_modules") -and (Test-Path ".\electron\package.json")

if ($electronReady) {
    Write-Host "Launching Electron…" -ForegroundColor Cyan
    Push-Location electron
    try {
        cmd /c npm start
    } finally {
        Pop-Location
        Write-Host ""
        Write-Host "Electron closed. Stopping backend…" -ForegroundColor Cyan
        if ($backendProc -and -not $backendProc.HasExited) {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "mwtn stopped." -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "Electron not installed — opening in your default browser." -ForegroundColor Yellow
    Write-Host "App URL : http://127.0.0.1:8000" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press Ctrl+C here to stop the backend when you're done." -ForegroundColor Yellow
    Write-Host ""
    try { Start-Process "http://127.0.0.1:8000" } catch { }
    try { Wait-Process -Id $backendProc.Id } catch { }
}
