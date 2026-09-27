#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

if [ ! -d "node_modules" ]; then
  echo "Missing frontend/node_modules. Run: cd frontend && npm install"
  exit 1
fi

exec npm run dev
