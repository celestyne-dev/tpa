#!/usr/bin/env bash
# Builds the prerendered frontend against a temporary local Flask API.
#
# Usage (from the repository root):
#   VITE_SITE_URL=https://your-domain VITE_ALLOW_INDEXING=false ./scripts/build-production.sh
#
# If PRERENDER_API_URL is already set (e.g. pointing at a running API), no
# temporary server is started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PRERENDER_PORT:-5055}"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then kill "$SERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

if [[ -z "${PRERENDER_API_URL:-}" ]]; then
  if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
    echo "backend/.venv not found. Run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
  echo "Starting temporary Flask API on 127.0.0.1:$PORT ..."
  (cd "$ROOT/backend" && exec .venv/bin/python -m flask --app wsgi run --port "$PORT") >/dev/null 2>&1 &
  SERVER_PID=$!
  export PRERENDER_API_URL="http://127.0.0.1:$PORT/api/v1"
  for _ in $(seq 1 50); do
    curl -fsS "$PRERENDER_API_URL/health" >/dev/null 2>&1 && break
    sleep 0.2
  done
fi

cd "$ROOT/frontend"
npm run build
echo "Static site ready in frontend/dist/"
