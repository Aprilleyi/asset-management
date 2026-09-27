#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

if [ ! -d ".venv" ]; then
  echo "Missing backend/.venv. Run: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

IFS=$'\t' read -r DATABASE_PATH API_HOST API_PORT < <(
  .venv/bin/python -c 'from app.core.config import settings; print(f"{settings.database_path}\t{settings.api_host}\t{settings.api_port}")'
)
.venv/bin/python -m app.db.migrate status --database "$DATABASE_PATH"
exec .venv/bin/uvicorn app.main:app --host "$API_HOST" --port "$API_PORT"
