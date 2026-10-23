#!/usr/bin/env bash
# Supervisor for watcher.py: single instance via flock, restarts on exit.
# Expects BEEPER_TOKEN, BEEPER_WEBHOOK_URL, BEEPER_WEBHOOK_SECRET in the environment (e.g. `set -a; . ../.env; set +a`).
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${BEEPER_STATE_DIR:-$DIR}/watcher.log"
exec 8>/tmp/beeper-watcher.lock
flock -n 8 || { echo "watcher already running"; exit 0; }
while true; do
  echo "$(date) starting watcher" >>"$LOG"
  python3 "$DIR/watcher.py" >>"$LOG" 2>&1
  echo "$(date) watcher exited rc=$?; restarting in 5s" >>"$LOG"
  sleep 5
done
