#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$ROOT_DIR/scripts/start_backend.sh" &
BACKEND_PID=$!

"$ROOT_DIR/scripts/start_frontend.sh" &
FRONTEND_PID=$!

echo "Backend address: see ASSET_MANAGER_API_HOST/PORT in backend/.env (defaults to 127.0.0.1:8000)"
echo "Frontend address: see VITE_DEV_PORT in frontend/.env.local (defaults to 127.0.0.1:5173)"

wait "$BACKEND_PID" "$FRONTEND_PID"
