#!/usr/bin/env bash
# Einrichtung im Codespace. Laeuft einmalig beim Erstellen.
#
# BEWUSST OHNE VENV. Der Container ist bereits die Isolation; ein venv
# darin bringt keinen Nutzen und hat zwei Fehlerquellen mitgebracht:
#
#   1. Im Ubuntu-noble-Image fehlt python3-venv. "python3 -m venv .venv"
#      legt das Verzeichnis an und scheitert dann an ensurepip -- zurueck
#      blieb ein halbes .venv ohne bin/activate. Danach war weder
#      "psp-radar" auf dem PATH noch "source .venv/bin/activate" moeglich.
#   2. Selbst mit venv haette pip an PEP 668 scheitern koennen.
#
# Der Dockerfile installiert seit Beginn ohne venv und laeuft in der CI
# fehlerfrei durch. Hier jetzt derselbe Weg.
#
# Ausserdem ohne "set -e": Ein einzelner Fehlschlag soll nicht das ganze
# Setup abbrechen und einen halb eingerichteten Codespace hinterlassen.
# Stattdessen wird am Ende geprueft und klar berichtet.
set -uo pipefail

echo "════════════════════════════════════════════"
echo "  psp-radar einrichten"
echo "════════════════════════════════════════════"
echo
echo "Python:     $(python3 --version 2>&1)"
echo "Chromium:   ${PLAYWRIGHT_BROWSERS_PATH:-Standardpfad}"
echo

echo "→ Abhaengigkeiten installieren"
if ! pip install --quiet -e ".[dev]"; then
  echo "  FEHLGESCHLAGEN. Nochmal mit ausfuehrlicher Ausgabe:"
  pip install -e ".[dev]"
fi

echo "→ Zugangscode-Datei anlegen (im Codespace absichtlich leer)"
[ -f .env ] || echo "PSP_RADAR_ACCESS_CODE=" > .env

echo
echo "════════════════════════════════════════════"
echo "  Selbsttest"
echo "════════════════════════════════════════════"
if command -v psp-radar >/dev/null 2>&1; then
  psp-radar doctor
  ERGEBNIS=$?
else
  echo "psp-radar ist nicht auf dem PATH — Installation fehlgeschlagen."
  echo "Ausweg: python3 -m psp_radar.cli doctor"
  ERGEBNIS=1
fi

echo
if [ "$ERGEBNIS" -eq 0 ]; then
  cat <<'FERTIG'
  Fertig. Die Oberflaeche oeffnet sich automatisch.
  Falls nicht: Reiter "Ports" → 8765 anklicken.

  Im Terminal:
    psp-radar doctor                              Umgebung pruefen
    psp-radar scan https://www.bergfreunde.de -v  ein Shop
    psp-radar batch shops.csv -o out.csv          eine Liste
    pytest -q                                     Tests
FERTIG
else
  cat <<'GESTOERT'
  ACHTUNG: Die Einrichtung ist nicht vollstaendig.
  Bitte die Ausgabe oben an Rocco/Claude weitergeben — daraus laesst
  sich die Ursache eindeutig bestimmen. Ohne vollstaendige Einrichtung
  bleiben Ergebnisse leer, und das sieht wie ein Erkennungsproblem aus,
  ist aber keins.
GESTOERT
fi
