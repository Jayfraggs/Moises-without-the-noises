#!/usr/bin/env bash
# run.sh — Start mwtn on macOS / Linux.
# Run ./activate.sh first (once).

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}$*${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
error() { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
info "=== mwtn ==="
echo ""

# ── Pre-flight ────────────────────────────────────────────────────────────────

[ -f "./venv/bin/activate" ]        || error "venv not found. Run ./activate.sh first."
[ -f "./frontend/static/index.html" ] || error "frontend/static/index.html missing. Project files may be incomplete."

ok "Frontend : OK"

# ── Start backend ─────────────────────────────────────────────────────────────

info "Starting mwtn backend..."

# shellcheck disable=SC1091
source ./venv/bin/activate
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# ── Poll until up ─────────────────────────────────────────────────────────────

printf "Waiting for backend"
WAITED=0
UP=false
while [ $WAITED -lt 30 ]; do
  sleep 1
  WAITED=$((WAITED + 1))
  printf "."
  if curl -sf "http://127.0.0.1:8000/api/songs" >/dev/null 2>&1; then
    UP=true
    break
  fi
done
echo ""

if $UP; then
  ok "Backend  : http://127.0.0.1:8000"
else
  warn "Backend didn't respond in 30 s. Check for errors above."
fi

# ── Open app ──────────────────────────────────────────────────────────────────

cleanup() {
  echo ""
  info "Stopping backend (PID $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
  ok "mwtn stopped."
}
trap cleanup EXIT INT TERM

if [ -d "./electron/node_modules" ] && [ -f "./electron/package.json" ]; then
  info "Launching Electron..."
  (cd electron && npm start)
else
  warn "Electron not installed — opening browser instead."
  echo ""
  echo -e "  App URL: ${CYAN}http://127.0.0.1:8000${NC}"
  echo "  Press Ctrl+C to stop."
  echo ""
  # Open in default browser
  if command -v open &>/dev/null; then        # macOS
    open "http://127.0.0.1:8000"
  elif command -v xdg-open &>/dev/null; then  # Linux
    xdg-open "http://127.0.0.1:8000" 2>/dev/null || true
  fi
  # Wait for backend process
  wait "$BACKEND_PID"
fi
