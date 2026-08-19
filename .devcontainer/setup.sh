#!/usr/bin/env bash
# Einrichtung im Codespace. Laeuft einmalig beim Erstellen.
#
# Bewusst OHNE "set -e": Ein Fehlschlag in einem Schritt soll nicht das
# ganze Setup abbrechen und einen halb eingerichteten Codespace
# hinterlassen. Stattdessen wird am Ende geprueft und klar berichtet.
set -uo pipefail

echo "=== psp-radar einrichten ==="

echo "-> Abhaengigkeiten installieren"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"

# Chromium liegt im Playwright-Image bereits unter /ms-playwright.
# Der Pfad kommt aus der Umgebungsvariablen des Images; nur zur Sicherheit
# nachgezogen, falls jemand das Image wechselt.
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/ms-playwright}"
echo "-> Chromium pruefen (PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH)"
if ! .venv/bin/python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    b.close()
" 2>/dev/null; then
  echo "   Chromium nicht startbar, wird nachgeladen ..."
  # Ohne --with-deps: die Systembibliotheken sind im Image enthalten,
  # und --with-deps braeuchte Root.
  .venv/bin/playwright install chromium
fi

if [ ! -f .env ]; then
  echo "PSP_RADAR_ACCESS_CODE=" > .env
fi

echo
echo "=== Selbsttest ==="
.venv/bin/psp-radar doctor
