<#
.SYNOPSIS
    One-time setup for the stem practice tool. Run this once while
    connected to the internet. After it completes, run.ps1/run.bat work
    fully offline.

.DESCRIPTION
    Does five things, in order:
      1. Creates a Python venv and installs backend deps (FastAPI, Demucs,
         librosa, CPU-only torch).
      2. Installs frontend npm deps and builds the React app to
         frontend/dist/ (the backend serves this directly -- no separate
         frontend server needed at runtime).
      3. Installs Electron's npm deps.
      4. Downloads the Demucs "htdemucs" model weights. This is the part
         that specifically needs internet -- Demucs pulls pretrained
         weights from Meta's model hub on first use, not from a single
         static file you could just Invoke-WebRequest. Forcing the
         download here, explicitly, means the model is cached before you
         ever try to use the app offline. If you re-run this script later,
         this step is fast (cache hit), not a re-download.
      5. Prints next steps.

    Safe to re-run -- venv creation and pip/npm installs are idempotent.
#>

$ErrorActionPreference = "Stop"

Write-Host "=== Stem Practice Tool: Setup ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. Python venv + backend deps ---

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "ERROR: Python not found on PATH. Install Python 3.10+ and re-run." -ForegroundColor Red
    exit 1
}

$pyVersionOutput = (python --version) 2>&1
Write-Host "Found $pyVersionOutput"

if (-not (Test-Path ".\venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
} else {
    Write-Host "Virtual environment already exists, reusing it."
}

Write-Host "Activating virtual environment..."
& ".\venv\Scripts\Activate.ps1"

Write-Host "Installing backend dependencies (torch + demucs are large, this can take several minutes)..." -ForegroundColor Cyan
python -m pip install --upgrade pip
pip install -r backend\requirements.txt

# --- 2. Frontend deps + build ---

$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Host "ERROR: npm not found on PATH. Install Node.js 18+ and re-run." -ForegroundColor Red
    exit 1
}

Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location frontend
npm install
Write-Host "Building frontend for production..."
npm run build
Pop-Location

if (-not (Test-Path ".\frontend\dist\index.html")) {
    Write-Host "ERROR: frontend build didn't produce dist/index.html. Check the npm output above." -ForegroundColor Red
    exit 1
}

# --- 3. Electron deps ---

Write-Host "Installing Electron dependencies..." -ForegroundColor Cyan
Push-Location electron
npm install
Pop-Location

# --- 4. Demucs model download (LOCAL PATH ONLY) ---
#
# This step is only needed if you are running Demucs locally (POST /api/import).
# If you are using the Google Colab path, demucs is not installed locally and
# this step is intentionally skipped.

Write-Host ""
python -c "import demucs" 2>&1 | Out-Null
$demucsInstalled = ($LASTEXITCODE -eq 0)

if ($demucsInstalled) {
    Write-Host "Downloading Demucs model (htdemucs, ~80MB)..." -ForegroundColor Cyan
    Write-Host "This is the step that specifically requires internet access."
    python -c "from demucs.pretrained import get_model; get_model('htdemucs'); print('Model cached successfully.')"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: model download failed. Check your internet connection and re-run activate.ps1." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Skipping Demucs model download - demucs is not installed (Colab path selected)." -ForegroundColor Yellow
    Write-Host "To cache model weights locally, uncomment demucs in backend\requirements.txt and re-run this script."
}


# --- 5. Done ---

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Run .\run.ps1 (or run.bat) to start the app. It will now work fully offline."
Write-Host ""
Write-Host "To add songs:"
Write-Host "  - Fast: process a song in colab_notebook.ipynb, then extract the output"
Write-Host "    zip into backend\data\"
Write-Host "  - Slow but fully local: use the 'Import a song' button in the app itself"
Write-Host "    (runs Demucs on this machine, expect 15-40 min per song on CPU)"
