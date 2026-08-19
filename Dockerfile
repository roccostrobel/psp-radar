# Fuer das spaetere Hosting. Im Codespace wird stattdessen .devcontainer/
# genutzt -- beide Wege teilen dieselben Schritte.
#
# WICHTIG zur Basis: Das offizielle Playwright-Image bringt Chromium und
# alle Systembibliotheken mit, was viel Bastelarbeit erspart. Die Variante
# ist aber entscheidend -- die Jammy-Basis (Ubuntu 22.04) liefert nur
# Python 3.10, und das Projekt verlangt 3.12. Deshalb Noble (Ubuntu 24.04).
# Dieser Fehler kostete einen CI-Durchlauf.
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PSP_RADAR_HEADLESS=1

# Abhaengigkeiten vor dem Quellcode kopieren, damit der Docker-Cache bei
# Codeaenderungen nicht jedes Mal verworfen wird.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python3 --version && pip install --no-cache-dir .

# Nicht als root laufen. Chromium in einem Container als root zu starten
# ist eine unnoetige Angriffsflaeche.
RUN useradd -m -u 10001 radar 2>/dev/null || true
RUN chown -R radar:radar /app
USER radar

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3).status==200 else 1)"

CMD ["psp-radar", "serve", "--host", "0.0.0.0", "--port", "8765"]
