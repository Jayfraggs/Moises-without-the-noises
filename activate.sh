#!/usr/bin/env bash
# activate.sh — One-time setup for mwtn on macOS / Linux.
# Run once, then use: ./run.sh to start the app.
# Safe to re-run — idempotent.

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}$*${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
error() { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
info "=== mwtn: Setup ==="
echo ""

# ── 1. Python 3.10+ ──────────────────────────────────────────────────────────

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  error "Python 3.10+ not found. Install it from https://python.org and re-run."
fi
ok "Python: $($PYTHON --version)"

# ── 2. Venv: create or repair ─────────────────────────────────────────────────

VENV_PYTHON="./venv/bin/python"
VENV_ACTIVATE="./venv/bin/activate"

if [ -f "$VENV_PYTHON" ] && [ -f "$VENV_ACTIVATE" ]; then
  ok "Virtual environment OK — reusing."
else
  if [ -d "./venv" ]; then
    warn "Virtual environment incomplete — rebuilding."
    rm -rf ./venv
  fi
  echo "Creating virtual environment..."
  "$PYTHON" -m venv venv
  ok "Virtual environment created."
fi

# shellcheck disable=SC1091
source "$VENV_ACTIVATE"

# ── 3. Backend deps ───────────────────────────────────────────────────────────

info "Upgrading pip..."
pip install --upgrade pip --quiet

info "Installing backend dependencies..."
pip install -r backend/requirements.txt

if [ -f "./tests/requirements-test.txt" ]; then
  info "Installing test dependencies..."
  pip install -r ./tests/requirements-test.txt
  ok "Test dependencies installed."
else
  warn "tests/requirements-test.txt not found; skipping test dependency install."
fi

ok "Backend dependencies installed."

# ── 4. Frontend check ─────────────────────────────────────────────────────────

echo ""
if [ -f "./frontend/static/index.html" ]; then
  ok "Frontend: frontend/static/index.html found."
else
  warn "frontend/static/index.html not found. Make sure the project files are intact."
fi

# ── 5. Electron (optional) ────────────────────────────────────────────────────

if command -v npm &>/dev/null && [ -f "./electron/package.json" ]; then
  info "Installing Electron dependencies..."
  (cd electron && npm install --silent)
  ok "Electron ready."
else
  warn "Electron skipped (npm not found or electron/package.json missing)."
  echo "  The app works in your browser without Electron."
fi

# ── 6. ffmpeg check ───────────────────────────────────────────────────────────

if command -v ffmpeg &>/dev/null; then
  ok "ffmpeg: $(command -v ffmpeg)"
else
  echo ""
  warn "ffmpeg not found on PATH."
  echo "  ffmpeg is required for audio export."
  echo ""
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  Install with Homebrew:  brew install ffmpeg"
  else
    echo "  Install with apt:       sudo apt install ffmpeg"
    echo "  or dnf:                 sudo dnf install ffmpeg"
  fi
  echo "  Then re-run ./activate.sh"
fi

# ── 7. Summary ────────────────────────────────────────────────────────────────

echo ""
ok "=== mwtn: Setup complete ==="
echo ""
echo "HOW TO ADD SONGS (recommended — Colab GPU, free):"
echo ""
echo "  1. Open colab/mwtn_notebook.ipynb in Google Colab."
echo "     Runtime → Change runtime type → T4 GPU (free tier works)."
echo ""
echo "  2. Edit Cell 3: set DRIVE_FILE_PATH to your song in Google Drive."
echo "     Run all cells (~2 min on GPU)."
echo ""
echo "  3. The output ZIP is saved to your Google Drive automatically."
echo "     Download it and drag it onto the mwtn window."
echo ""
echo "  ⚠  First Colab run downloads ~3.5 GB (Demucs + Whisper models)."
echo "     Do this on Wi-Fi."
echo ""
echo "  Alternative (local, CPU, slow):"
echo "  Uncomment torch + demucs in backend/requirements.txt, re-run ./activate.sh,"
echo "  then use the Import button in the mwtn window."
echo ""
echo "START THE APP:"
echo -e "  ${CYAN}./run.sh${NC}"
echo ""
