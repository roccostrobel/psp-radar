#!/usr/bin/env bash
# Einmalige Einrichtung auf diesem Rechner.
#
# Danach reicht ein Doppelklick auf start-lokal.command.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo
echo "psp-radar einrichten"
echo "────────────────────────────────────────"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "→ uv installieren"
  curl -fsSL https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# WICHTIG: VIRTUAL_ENV muss weg, sonst installiert uv in eine fremde
# Umgebung. Das hat schon einmal eine halbe Stunde gekostet.
unset VIRTUAL_ENV || true

echo "→ Umgebung anlegen"
[ -d .venv ] || uv venv --python 3.12

echo "→ Abhaengigkeiten installieren"
uv pip install --python "$PWD/.venv/bin/python" -e ".[dev]"

echo "→ Chromium passend zur Playwright-Version holen"
# Passend zur installierten Bibliothek, nicht zu einer festen Version.
./.venv/bin/playwright install chromium

echo
echo "Selbsttest"
echo "────────────────────────────────────────"
./.venv/bin/psp-radar doctor
ERGEBNIS=$?

echo
if [ "$ERGEBNIS" -eq 0 ]; then
  echo "Fertig. Ab jetzt genuegt ein Doppelklick auf:"
  echo "  start-lokal.command"
else
  echo "Einrichtung unvollstaendig — siehe Tabelle oben."
fi
exit $ERGEBNIS
