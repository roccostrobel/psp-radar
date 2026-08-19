#!/usr/bin/env bash
# Laeuft bei jedem Start des Codespace.
set -uo pipefail

if ! command -v psp-radar >/dev/null 2>&1; then
  echo "psp-radar fehlt — bitte 'bash .devcontainer/setup.sh' ausfuehren."
  exit 0
fi

# Nicht doppelt starten
if pgrep -f "psp-radar serve" >/dev/null 2>&1; then
  echo "psp-radar laeuft bereits auf Port 8765"
  exit 0
fi

nohup psp-radar serve --host 0.0.0.0 --port 8765 --no-browser \
  > /tmp/psp-radar.log 2>&1 &

sleep 3
echo "psp-radar gestartet. Log: /tmp/psp-radar.log"
