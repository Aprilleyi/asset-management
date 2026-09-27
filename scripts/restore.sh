#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"
PYTHON_BIN="${ASSET_MANAGER_PYTHON:-$ROOT_DIR/backend/.venv/bin/python}"
exec "$PYTHON_BIN" -m app.db.backup_cli restore "$@"
