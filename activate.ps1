<#
.SYNOPSIS
    One-time setup for mwtn. Run this once, then use run.ps1 to start the app.

.DESCRIPTION
    1. Validates Python 3.10+ is on PATH.
    2. Recreates the venv if it's broken (missing Activate.ps1) or creates it fresh.
    3. Installs backend Python dependencies into the venv.
    4. Installs Electron npm dependencies (optional — for the desktop wrapper).
    5. Verifies ffmpeg is reachable and prints a clear warning if not.
    6. Prints next steps.

    Safe to re-run. If the venv is healthy it is reused; only broken venvs
    are deleted and rebuilt.

.NOTES
    torch and demucs are NOT installed by default — mwtn uses Google Colab
    for ML processing. To enable the slow local-import path, uncomment those
    lines in backend\requirements.txt and re-run this script.
#>

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== mwtn: Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. Python 3.10+ check ─────────────────────────────────────────────────────

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "ERROR: 'python' not found on PATH." -ForegroundColor Red
    Write-Host "       Install Python 3.10+ from https://python.org and re-run." -ForegroundColor Yellow
    exit 1
}

$pyVerRaw  = (python --version) 2>&1
$pyVerStr  = ($pyVerRaw -replace 'Python ', '')
$pyParts   = $pyVerStr.Split('.')
$pyMajor   = [int]$pyParts[0]
$pyMinor   = [int]$pyParts[1]

Write-Host "Python: $pyVerRaw" -ForegroundColor Green

if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
    Write-Host "ERROR: Python 3.10 or newer is required (found $pyVerStr)." -ForegroundColor Red
    exit 1
}

# ── 2. Venv: create or repair ─────────────────────────────────────────────────

$venvActivate = ".\venv\Scripts\Activate.ps1"
$venvPython   = ".\venv\Scripts\python.exe"

$needsCreate = $true
if (Test-Path $venvPython) {
    if (Test-Path $venvActivate) {
        Write-Host "Virtual environment OK — reusing." -ForegroundColor Green
        $needsCreate = $false
    } else {
        Write-Host "Virtual environment is incomplete (Activate.ps1 missing). Rebuilding…" -ForegroundColor Yellow
        Remove-Item -Recurse -Force ".\venv" -ErrorAction SilentlyContinue
    }
} elseif (Test-Path ".\venv") {
    Write-Host "Virtual environment folder exists but Python binary is missing. Rebuilding…" -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".\venv" -ErrorAction SilentlyContinue
}

if ($needsCreate) {
    Write-Host "Creating virtual environment…"
    python -m venv venv
    if (-not (Test-Path $venvActivate)) {
        Write-Host "ERROR: venv was created but Activate.ps1 is still missing." -ForegroundColor Red
        Write-Host "       Try running: python -m venv --clear venv" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "Virtual environment created." -ForegroundColor Green
}

# ── 3. Activate + install deps ────────────────────────────────────────────────

Write-Host "Activating virtual environment…"
& $venvActivate

Write-Host "Upgrading pip…"
python -m pip install --upgrade pip --quiet

Write-Host "Installing backend dependencies…" -ForegroundColor Cyan
pip install -r backend\requirements.txt

Write-Host "Backend dependencies installed." -ForegroundColor Green

# ── 4. Frontend check ─────────────────────────────────────────────────────────

Write-Host ""
if (Test-Path ".\frontend\static\index.html") {
    Write-Host "Frontend: OK (frontend\static\index.html found)" -ForegroundColor Green
} else {
    Write-Host "WARNING: frontend\static\index.html not found." -ForegroundColor Yellow
    Write-Host "         Make sure you extracted the full project zip." -ForegroundColor Yellow
}

# ── 5. Electron (optional) ────────────────────────────────────────────────────

$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if ($npmCmd -and (Test-Path ".\electron\package.json")) {
    Write-Host "Installing Electron dependencies…" -ForegroundColor Cyan
    Push-Location electron
    npm install --silent 2>&1 | Out-Null
    Pop-Location
    Write-Host "Electron ready." -ForegroundColor Green
} else {
    Write-Host "Electron: skipped (npm not found or electron/package.json missing)." -ForegroundColor Yellow
    Write-Host "          The app works in your browser without Electron." -ForegroundColor Yellow
}

# ── 6. ffmpeg check ───────────────────────────────────────────────────────────

$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
    Write-Host "ffmpeg: found at $($ffmpegCmd.Source)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: ffmpeg not found on PATH." -ForegroundColor Yellow
    Write-Host "         ffmpeg is required for audio export (mixdown, stems zip)." -ForegroundColor Yellow
    Write-Host "         Install it from https://ffmpeg.org/download.html" -ForegroundColor Yellow
    Write-Host "         Then add it to your PATH and re-run activate.ps1." -ForegroundColor Yellow
}

# ── 7. Summary ────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== mwtn: Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "HOW TO ADD SONGS (recommended — Colab GPU, free):" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Open colab\mwtn_notebook.ipynb in Google Colab."
Write-Host "     Runtime → Change runtime type → T4 GPU (free tier works)."
Write-Host ""
Write-Host "  2. Edit Cell 3: set DRIVE_FILE_PATH to your song in Google Drive."
Write-Host "     Run all cells (takes ~2 min on GPU)."
Write-Host ""
Write-Host "  3. The output ZIP is saved to your Google Drive automatically."
Write-Host "     Download it, then drag it onto the mwtn window — done."
Write-Host ""
Write-Host "  Or: extract the ZIP so backend\data\<song_id>\manifest.json exists."
Write-Host "      The app picks it up with no restart."
Write-Host ""
Write-Host "  ⚠  First Colab run downloads ~3.5 GB (Demucs + Whisper models)."
Write-Host "     Do that on Wi-Fi." -ForegroundColor Yellow
Write-Host ""
Write-Host "ALTERNATIVE (local, CPU-only, slow):"
Write-Host "  Uncomment torch + demucs in backend\requirements.txt, re-run activate.ps1,"
Write-Host "  then use the Import button in the mwtn window."
Write-Host ""
Write-Host "START THE APP:"
Write-Host "  .\run.ps1" -ForegroundColor Cyan
Write-Host ""
