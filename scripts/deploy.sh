#!/usr/bin/env bash
# For later server use, after a reviewed first migration and verified backup.
set -euo pipefail

if [ "${1:-}" != "--execute" ]; then
  echo "Usage: scripts/deploy.sh --execute (requires an existing Alembic-managed production DB)" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree must be clean before deployment" >&2
  exit 1
fi
if [ ! -f runtime/data/asset_prod.sqlite3 ]; then
  echo "Production DB is missing; use the reviewed first-deployment procedure" >&2
  exit 1
fi

git pull --ff-only
docker compose build
docker compose run --rm --no-deps backend python -m app.db.migrate managed --database /srv/runtime/data/asset_prod.sqlite3
docker compose run --rm --no-deps backend python -m app.db.backup_cli backup --source /srv/runtime/data/asset_prod.sqlite3 --backup-dir /srv/runtime/backups --type migration
docker compose stop frontend backend
docker compose run --rm --no-deps backend python -m app.db.migrate upgrade --database /srv/runtime/data/asset_prod.sqlite3
docker compose up -d --no-deps backend
docker compose up -d --no-deps frontend
docker compose ps
