#!/usr/bin/env bash
set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
BACKEND_LABEL="com.leyi.personal-asset-manager.backend"
FRONTEND_LABEL="com.leyi.personal-asset-manager.frontend"
BACKEND_PLIST="$LAUNCH_AGENTS_DIR/$BACKEND_LABEL.plist"
FRONTEND_PLIST="$LAUNCH_AGENTS_DIR/$FRONTEND_LABEL.plist"

launchctl bootout "gui/$(id -u)" "$BACKEND_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$FRONTEND_PLIST" >/dev/null 2>&1 || true
rm -f "$BACKEND_PLIST" "$FRONTEND_PLIST"

echo "Autostart removed."
