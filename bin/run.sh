#!/usr/bin/env bash
# =========================================================
# Projekt:Alpha — local run (real backend + real frontend + MCP server)
#   backend : FastAPI on :8000 (uvicorn)
#   frontend: Vite dev server on :3000 (proxies /api -> :8000)
#   mcp     : MCP server on :4100 (Streamable HTTP transport)
#
# Usage:
#   ./bin/run.sh            # starts backend + frontend
#   ./bin/run.sh backend    # backend only
#   ./bin/run.sh frontend   # frontend only
#   ./bin/run.sh mcp        # MCP server only (HTTP on :4100)
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

run_mcp() {
  cd mcp-server
  if [ ! -d node_modules ]; then
    echo "Installing MCP server dependencies ..."
    npm install
  fi
  cd ..
  echo "Starting MCP server on http://0.0.0.0:${MCP_PORT:-4100}/mcp"
  cd mcp-server && MCP_PORT="${MCP_PORT:-4100}" ALPHA_BACKEND_URL="${ALPHA_BACKEND_URL:-http://127.0.0.1:8000}" npx tsx src/http-server.ts
}

case "${1:-all}" in
  backend)   run_backend ;;
  frontend)  run_frontend ;;
  mcp)       run_mcp ;;
  all)
    run_backend &
    BACKEND_PID=$!
    trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
    run_frontend
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend|mcp]"
    exit 2
    ;;
esac
