#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/personal-asset-manager"
BACKEND_LABEL="com.leyi.personal-asset-manager.backend"
FRONTEND_LABEL="com.leyi.personal-asset-manager.frontend"
BACKEND_PLIST="$LAUNCH_AGENTS_DIR/$BACKEND_LABEL.plist"
FRONTEND_PLIST="$LAUNCH_AGENTS_DIR/$FRONTEND_LABEL.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

launchctl bootout "gui/$(id -u)" "$BACKEND_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "$FRONTEND_PLIST" >/dev/null 2>&1 || true

cat > "$BACKEND_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$BACKEND_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/start_backend.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/backend.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/backend.err.log</string>
</dict>
</plist>
PLIST

cat > "$FRONTEND_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$FRONTEND_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/start_frontend.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/frontend.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/frontend.err.log</string>
</dict>
</plist>
PLIST

launchctl bootstrap "gui/$(id -u)" "$BACKEND_PLIST"
launchctl bootstrap "gui/$(id -u)" "$FRONTEND_PLIST"
launchctl kickstart -k "gui/$(id -u)/$BACKEND_LABEL"
launchctl kickstart -k "gui/$(id -u)/$FRONTEND_LABEL"

echo "Autostart installed."
echo "Frontend: http://127.0.0.1:5173/"
echo "Backend health: http://127.0.0.1:8000/health"
echo "Logs: $LOG_DIR"
