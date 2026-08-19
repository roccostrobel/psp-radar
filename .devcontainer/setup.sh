#!/usr/bin/env bash
# Einrichtung im Codespace. Laeuft einmalig beim Erstellen.
#
# Ziel: Wer den Codespace startet, muss nichts eingeben. Kein Terminal,
# keine Befehle, keine Entscheidungen. Danach ist die Oberflaeche offen.
set -euo pipefail

echo "-> uv installieren"
curl -fsSL https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "-> Umgebung anlegen"
# VIRTUAL_ENV muss weg, sonst installiert uv in eine fremde Umgebung --
# das hat im Vorgaengerprojekt eine halbe Stunde gekostet.
unset VIRTUAL_ENV || true
uv venv --python 3.12
uv pip install --python "$PWD/.venv/bin/python" -e ".[dev]"

echo "-> Chromium installieren"
# --with-deps zieht die Systembibliotheken mit, die Chromium unter Debian
# braucht. Ohne das startet der Browser mit einer unverstaendlichen Meldung.
.venv/bin/playwright install --with-deps chromium

echo "-> Signatur-Datenbank pruefen"
.venv/bin/psp-radar signatures --check

# Im Codespace ist der Port privat und nur fuer den angemeldeten Nutzer
# erreichbar. Ein Zugangscode ist hier nicht noetig, beim Hosting schon.
if [ ! -f .env ]; then
  echo "PSP_RADAR_ACCESS_CODE=" > .env
fi

cat <<'BANNER'

  psp-radar ist eingerichtet.

  Die Oberflaeche oeffnet sich automatisch. Falls nicht:
  im Reiter "Ports" auf 8765 klicken.

  Im Terminal:
    .venv/bin/psp-radar scan https://beispielshop.de
    .venv/bin/psp-radar batch shops.csv -o ergebnisse.csv
    .venv/bin/pytest -q

BANNER
