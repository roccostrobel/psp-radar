"""Klickt die Oberfläche im echten Browser durch und prüft das Ergebnis.

Der Test, der gefehlt hat. Die Vertragstests in tests/test_web_api_vertrag.py
fangen den Endpunkt-Fehler ab, aber nur dieser Lauf beweist, dass ein Klick
auf "Analysieren" am Ende auch ein sichtbares Ergebnis erzeugt.

Erwartet einen laufenden Server:

    psp-radar serve --no-browser --port 8765
    python scripts/verify_ui.py [--liste]
"""

from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

UI = "http://127.0.0.1:8765"
OUT = "/tmp"


async def pruefe(liste: bool, modus: str = "statisch", shop: str = "https://www.snocks.com") -> int:
    fehler: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1100, "height": 950}, device_scale_factor=2)

        konsole: list[str] = []
        page.on("console", lambda m: konsole.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: konsole.append(f"pageerror: {e}"))

        await page.goto(UI, wait_until="networkidle")
        await page.screenshot(path=f"{OUT}/radar_start.png", full_page=True)
        print("Startseite geladen")

        await page.click(f"label:has(input[value={modus}])")

        if liste:
            await page.click("#tab-liste")
            await page.fill("#urls", f"{shop}\nhttps://www.waterdrop.de")
            # Im Listen-Modus darf das Einzelfeld nicht mehr sichtbar sein
            if await page.locator("#url").is_visible():
                fehler.append("Einzelfeld bleibt im Listen-Modus sichtbar")
        else:
            await page.fill("#url", shop)
            if await page.locator("#feld-liste").is_visible():
                fehler.append("Listenfeld bleibt im Einzel-Modus sichtbar")

        await page.click("#go")
        print("Analyse gestartet")

        # Auf ein Ergebnis warten — nicht auf eine Dauer
        fertig = False
        for _ in range(80):
            await page.wait_for_timeout(1000)
            if not await page.locator("#go").is_disabled():
                fertig = True
                break

        if not fertig:
            fehler.append("Analyse wurde nach 80 s nicht abgeschlossen")

        inhalt = await page.locator("#out").inner_text()
        await page.screenshot(path=f"{OUT}/radar_ergebnis.png", full_page=True)

        if not inhalt.strip():
            fehler.append("Ergebnisbereich ist leer — der Klick hat nichts bewirkt")
        if liste and inhalt.lstrip().startswith("0 von"):
            fehler.append(f"Zähler steht auf 0, obwohl Ergebnisse da sind: {inhalt[:60]!r}")
        if "fehlgeschlagen" in inhalt.lower() or "HTTP 4" in inhalt or "HTTP 5" in inhalt:
            fehler.append(f"Fehlermeldung in der Oberfläche: {inhalt[:200]}")
        if konsole:
            fehler.append("JavaScript-Fehler: " + " | ".join(konsole[:3]))

        print("\n--- Ergebnisbereich ---")
        print(inhalt[:700] or "(leer)")

        await browser.close()

    print()
    if fehler:
        for f in fehler:
            print(f"FEHLER: {f}")
        return 1
    print("OK — Klick erzeugt ein sichtbares Ergebnis, keine JavaScript-Fehler.")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    modus = next((a.split("=")[1] for a in sys.argv if a.startswith("--modus=")), "statisch")
    shop = args[0] if args else "https://www.snocks.com"
    sys.exit(asyncio.run(pruefe("--liste" in sys.argv, modus, shop)))
