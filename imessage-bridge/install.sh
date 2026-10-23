#!/bin/bash
# Installs the iMessage bridge on a Mac. Usage: bash install.sh [/path/to/python3]
# Copy config.example.json to config.json and fill it in first.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "Run this on the Mac."; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"; D="$HOME/.imessage-bridge"; LABEL=com.example.imessage-bridge
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
[ -f "$HERE/config.json" ] || { echo "Create $HERE/config.json from config.example.json first."; exit 1; }
PY="${1:-}"
if [ -z "$PY" ]; then
  # Resolve the REAL interpreter (macOS checks Full Disk Access on the resolved binary, not a symlink/shim).
  PY=$(/usr/bin/python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')
  APP="$(dirname "$PY")/../Resources/Python.app/Contents/MacOS/Python"
  [ -x "$APP" ] && PY="$(cd "$(dirname "$APP")" && pwd)/Python"
fi
"$PY" -c 'import sqlite3' || { echo "Python at $PY doesn't work"; exit 1; }
mkdir -p "$D" && chmod 700 "$D"; umask 077
cp "$HERE/bridge.py" "$D/bridge.py"; cp "$HERE/config.json" "$D/config.json"; chmod 600 "$D/config.json"
sed -e "s#__PYTHON__#$PY#" -e "s#__HOME__#$HOME#g" "$HERE/$LABEL.plist" > "$PLIST"
echo "Python used: $PY"
echo "Grant it Full Disk Access: System Settings > Privacy & Security > Full Disk Access > + > Cmd+Shift+G > paste the path above."
if [ "$("$PY" "$D/bridge.py" --check-db)" != "ok" ]; then echo "chat.db not readable yet - grant FDA, then re-run."; exit 1; fi
"$PY" "$D/bridge.py" --init-cursor >/dev/null   # start from now; never replays history
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Test the webhook with: $PY $D/bridge.py --test"
