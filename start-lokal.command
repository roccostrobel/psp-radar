#!/usr/bin/env bash
# Doppelklick-Starter fuer psp-radar.
#
# Absichtlich ein .command im Projektverzeichnis: macOS fuehrt solche
# Dateien beim Doppelklick im Terminal aus. Kein Befehl zum Merken, aber
# die Ausgabe bleibt sichtbar -- falls etwas schiefgeht, steht der Grund da,
# statt lautlos zu verschwinden.
cd "$(dirname "$0")" || exit 1

PORT=8765
GRUEN=$'\033[32m'; ROT=$'\033[31m'; GELB=$'\033[33m'; AUS=$'\033[0m'; FETT=$'\033[1m'

echo
echo "${FETT}psp-radar${AUS}"
echo "────────────────────────────────────────"
echo

if [ ! -x .venv/bin/psp-radar ]; then
  echo "${ROT}Nicht eingerichtet.${AUS}"
  echo "Bitte einmalig im Terminal ausfuehren:"
  echo
  echo "  cd \"$(pwd)\""
  echo "  ./einrichten.sh"
  echo
  read -r -p "Mit Enter schliessen "
  exit 1
fi

# Laeuft schon etwas auf dem Port? Dann nicht doppelt starten.
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "${GELB}Laeuft bereits.${AUS} Oeffne die Oberflaeche ..."
  open "http://localhost:$PORT"
  sleep 1
  exit 0
fi

echo "Umgebung pruefen ..."
if ! ./.venv/bin/psp-radar doctor; then
  echo
  echo "${ROT}Die Umgebung ist nicht vollstaendig.${AUS}"
  echo "Die Tabelle oben zeigt, woran es liegt."
  echo
  read -r -p "Mit Enter schliessen "
  exit 1
fi

echo
echo "Server starten ..."
./.venv/bin/psp-radar serve --port $PORT --no-browser &
SERVER=$!

# Auf Bereitschaft warten, nicht auf eine feste Dauer
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "${ROT}Server ist nicht hochgekommen.${AUS}"
  read -r -p "Mit Enter schliessen "
  exit 1
fi

echo "${GRUEN}Bereit.${AUS} Oeffne http://localhost:$PORT"
open "http://localhost:$PORT"

echo
echo "────────────────────────────────────────"
echo "Dieses Fenster offen lassen, solange du"
echo "das Tool nutzt. Beenden mit ${FETT}Strg+C${AUS}"
echo "oder indem du das Fenster schliesst."
echo "────────────────────────────────────────"
echo

# Server im Vordergrund halten, damit Strg+C ihn beendet
trap 'echo; echo "psp-radar beendet."; kill $SERVER 2>/dev/null; exit 0' INT TERM
wait $SERVER
