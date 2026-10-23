#!/usr/bin/env bash
# Supervisor: keeps Beeper Desktop running on DISPLAY (default :2). Single instance via flock.
export DISPLAY="${BEEPER_DISPLAY:-:2}"
APP="${BEEPER_APPIMAGE:-$HOME/Applications/Beeper.AppImage}"
LOG="${BEEPER_LOG:-$(cd "$(dirname "$0")" && pwd)/beeper.log}"
exec 9>/tmp/beeper-supervisor.lock
flock -n 9 || { echo "supervisor already running"; exit 0; }
export APPIMAGE_EXTRACT_AND_RUN=1
while true; do
  # wait for the X display to exist
  until xwininfo -root >/dev/null 2>&1; do sleep 5; done
  echo "$(date) starting Beeper on $DISPLAY" >>"$LOG"
  "$APP" --appimage-extract-and-run --no-sandbox >>"$LOG" 2>&1
  echo "$(date) Beeper exited rc=$? ; restarting in 5s" >>"$LOG"
  sleep 5
done
