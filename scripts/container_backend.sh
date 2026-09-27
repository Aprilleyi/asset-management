#!/bin/sh
set -eu

python -m app.db.migrate status --database "$ASSET_MANAGER_DATABASE_PATH"
exec uvicorn app.main:app --host "${ASSET_MANAGER_API_HOST:-0.0.0.0}" --port "${ASSET_MANAGER_API_PORT:-8000}" --workers 1
