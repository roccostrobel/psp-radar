# Fuer das spaetere Hosting. Im Codespace wird stattdessen
# .devcontainer/ genutzt -- beide Wege teilen dieselben Schritte.
#
# Basis ist das offizielle Playwright-Image: Chromium und alle
# Systembibliotheken sind enthalten. Selbst zusammenzusetzen kostet
# nur Zeit und bringt genau nichts.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PSP_RADAR_HEADLESS=1

# Abhaengigkeiten vor dem Quellcode kopieren, damit der Docker-Cache
# bei Codeaenderungen nicht jedes Mal verworfen wird.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Nicht als root laufen. Chromium in einem Container als root zu starten
# ist eine unnoetige Angriffsflaeche.
RUN useradd -m -u 10001 radar && chown -R radar:radar /app
USER radar

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3).status==200 else 1)"

CMD ["psp-radar", "serve", "--host", "0.0.0.0", "--port", "8765"]
