<# One-time mwtn setup. Safe to run again. #>
$ErrorActionPreference = "Stop"
Write-Host "=== mwtn: Setup ===" -ForegroundColor Cyan
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { Write-Host "ERROR: Python 3.10 or newer was not found on PATH." -ForegroundColor Red; exit 1 }
$versionText = ((python --version) 2>&1).ToString() -replace '^Python ', ''
$versionParts = $versionText.Split('.')
if ([int]$versionParts[0] -lt 3 -or ([int]$versionParts[0] -eq 3 -and [int]$versionParts[1] -lt 10)) { Write-Host "ERROR: Python 3.10 or newer is required (found $versionText)." -ForegroundColor Red; exit 1 }
Write-Host "Python: $versionText" -ForegroundColor Green
$venvPath = Join-Path $PSScriptRoot 'venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$venvActivate = Join-Path $venvPath 'Scripts\Activate.ps1'
if (-not (Test-Path $venvPython) -or -not (Test-Path $venvActivate)) {
    if (Test-Path $venvPath) { Remove-Item -LiteralPath $venvPath -Recurse -Force }
    Write-Host "Creating virtual environment..."
    python -m venv $venvPath
}
if (-not (Test-Path $venvActivate)) { Write-Host "ERROR: virtual environment activation script was not created." -ForegroundColor Red; exit 1 }
Write-Host "Activating virtual environment..."
& $venvActivate
$env:PYTHONPATH = $PSScriptRoot + ";" + $env:PYTHONPATH
Write-Host "Upgrading pip..."
python -m pip install --upgrade pip --quiet
Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
python -m pip install -r (Join-Path $PSScriptRoot 'backend\requirements.txt')
$testRequirements = Join-Path $PSScriptRoot 'tests\requirements-test.txt'
if (Test-Path $testRequirements) { Write-Host "Installing test dependencies..." -ForegroundColor Cyan; python -m pip install -r $testRequirements }
$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCommand) { Write-Host "ffmpeg: found at $($ffmpegCommand.Source)" -ForegroundColor Green } else { Write-Host "WARNING: ffmpeg was not found on PATH." -ForegroundColor Yellow }
Write-Host "=== mwtn: Setup complete ===" -ForegroundColor Green
Write-Host "Start the app with: .\run.ps1" -ForegroundColor Cyan
