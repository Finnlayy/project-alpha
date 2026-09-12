#!/usr/bin/env bash
# =========================================================
# Projekt:Alpha — local run (real backend + real frontend)
#   backend : FastAPI on :8000 (uvicorn)
#   frontend: Vite dev server on :3000 (proxies /api -> :8000)
#
# Usage:
#   ./bin/run.sh            # starts both
#   ./bin/run.sh backend    # backend only
#   ./bin/run.sh frontend   # frontend only
#
# Credentials (optional, real values only — the system degrades
# to paper/offline states explicitly when absent):
#   cp .env.example .env   and fill in the Kraken API keys
# =========================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "Creating virtualenv .venv ..."
  "$PY" -m venv .venv
fi
VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "Missing .venv — create it with: python3 -m venv .venv"
  exit 1
fi
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

run_backend() {
  echo "Starting backend on http://0.0.0.0:8000 (Ctrl+C to stop)"
  "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
}

run_frontend() {
  if [ ! -d node_modules ]; then
    echo "Installing npm dependencies ..."
    npm install
  fi
  echo "Starting frontend on http://0.0.0.0:3000 (proxies /api to :${BACKEND_PORT:-8000})"
  npx vite --host 0.0.0.0 --port "${FRONTEND_PORT:-3000}"
}

case "${1:-all}" in
  backend)   run_backend ;;
  frontend)  run_frontend ;;
  all)
    run_backend &
    BACKEND_PID=$!
    trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
    run_frontend
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend]"
    exit 2
    ;;
esac
