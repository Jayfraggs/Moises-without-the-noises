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

# ── Clear stale port 8000 listener (Windows bind fix) ───────────────────────

$staleListeners = @(Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -gt 0 })

if ($staleListeners.Count -gt 0) {
    Write-Host "Port 8000 is already in use; clearing stale listener(s)…" -ForegroundColor Yellow
    foreach ($processId in $staleListeners) {
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "  Stopped PID $processId" -ForegroundColor Yellow
        } catch {
            Write-Host "  Could not stop PID $processId; it may have already exited." -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 1
}

# ── Start backend ─────────────────────────────────────────────────────────────

Write-Host "Starting mwtn backend…" -ForegroundColor Cyan

$activatePath = (Resolve-Path $venvActivate).Path
$repoRoot     = (Resolve-Path ".").Path

$backendCmd = `
  "`$host.UI.RawUI.WindowTitle = 'mwtn backend'; " + `
  "& '$activatePath'; " + `
  "Set-Location '$repoRoot'; " + `
  "`$env:PYTHONPATH = '$repoRoot'; " + `
  "uvicorn backend.main:app --host 127.0.0.1 --port 8000"

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

Start-Sleep -Seconds 2
Write-Host ""
Write-Host "--- MWTN Health Check ---" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 5
    Write-Host ("  Backend:    {0}" -f $health.status.ToUpper()) -ForegroundColor Green
    foreach ($check in $health.checks.PSObject.Properties) {
        $st = $check.Value.status
        $color = if ($st -eq "ok") { "Green" } elseif ($st -eq "not_installed") { "DarkGray" } else { "Yellow" }
        Write-Host ("  {0,-20} {1}" -f $check.Name, $st) -ForegroundColor $color
    }
} catch {
    Write-Host "  Could not reach backend health endpoint." -ForegroundColor Yellow
    Write-Host "  Backend may still be starting up." -ForegroundColor DarkGray
}
Write-Host "-------------------------" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mobile data tip: Heavy processing runs on Google Colab, not locally." -ForegroundColor DarkCyan
Write-Host "   Only upload/download costs apply (~60-200 MB per song via Colab)." -ForegroundColor DarkGray
Write-Host ""

# ── Launch app ────────────────────────────────────────────────────────────────

$electronExe = Join-Path $PSScriptRoot "electron\node_modules\.bin\electron.cmd"

if (Test-Path $electronExe) {
    Write-Host "Launching Electron shell..." -ForegroundColor Cyan
    $electronProc = Start-Process -FilePath $electronExe -ArgumentList "." -WorkingDirectory (Join-Path $PSScriptRoot "electron") -PassThru
    try {
        Wait-Process -Id $electronProc.Id -ErrorAction SilentlyContinue
    } finally {
        if ($backendProc -and -not $backendProc.HasExited) {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host ""
    Write-Host "Electron not built - opening browser UI instead." -ForegroundColor DarkGray
    Write-Host "App URL : http://localhost:5173" -ForegroundColor Cyan
    Write-Host ""
    Write-Host 'Press Ctrl+C here to stop the backend when you are done.' -ForegroundColor Yellow
    Write-Host ""
    Start-Process "http://localhost:5173" -ErrorAction SilentlyContinue
    try { Wait-Process -Id $backendProc.Id -ErrorAction SilentlyContinue } catch { }
}
