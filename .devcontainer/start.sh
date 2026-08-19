#!/usr/bin/env bash
# Laeuft bei jedem Start des Codespace.
#
# Eigenes Skript statt einer Zeile in devcontainer.json, damit der Server
# nicht doppelt startet und das Log auffindbar bleibt.
set -uo pipefail

if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "psp-radar laeuft bereits auf Port 8765"
  exit 0
fi

nohup .venv/bin/psp-radar serve --host 0.0.0.0 --port 8765 --no-browser \
  > /tmp/psp-radar.log 2>&1 &

echo "psp-radar gestartet. Log: /tmp/psp-radar.log"
