"""Warten auf Ereignisse statt auf Sekunden.

Das Herzstück der Beschleunigung — und gleichzeitig eine
Zuverlässigkeitsverbesserung, weshalb hier nichts abgewogen werden muss.

Der Vorgänger enthielt 57 Sekunden fest verdrahtetes `asyncio.sleep()` über
33 Stellen. Ein `sleep(3.0)` nach dem Klick auf "Zur Kasse" hat zwei
Probleme auf einmal:

- Bei einem schnellen Shop sind 2,7 dieser 3 Sekunden verschenkt.
- Bei einem langsamen Shop reichen 3 Sekunden nicht, und das Tool liest
  einen halbfertigen Zustand aus. Das Ergebnis ist dann nicht langsam,
  sondern falsch.

Die Funktionen hier warten stattdessen auf das konkrete Ereignis, auf das
es ankommt, mit einer Obergrenze als Notausgang. Schnelle Shops sind sofort
fertig, langsame bekommen die Zeit, die sie brauchen.

Grundregel: **Nie auf eine Dauer warten, immer auf eine Bedingung.**
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

#: Abfrageintervall beim Warten auf Bedingungen. 120 ms ist fein genug,
#: dass es sich nicht wie Warten anfühlt, und grob genug, dass das Abfragen
#: selbst keine Last erzeugt.
POLL_INTERVAL = 0.12


async def wait_until(
    predicate: Callable[[], Awaitable[bool]],
    timeout: float,
    *,
    interval: float = POLL_INTERVAL,
) -> bool:
    """Wartet, bis `predicate` wahr wird. Gibt zurück, ob es eingetreten ist.

    Fehler in der Prüffunktion gelten als "noch nicht" — bei einer Seite,
    die gerade neu lädt, greifen DOM-Abfragen zwangsläufig manchmal ins
    Leere, und das ist kein Grund abzubrechen.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await predicate():
                return True
        except (PlaywrightError, Exception):
            pass
        await asyncio.sleep(interval)
    return False


async def wait_for_network_quiet(
    request_count: Callable[[], int],
    *,
    quiet_for: float = 0.7,
    timeout: float = 8.0,
) -> bool:
    """Wartet, bis für `quiet_for` Sekunden kein neuer Request mehr kam.

    Bewusst nicht Playwrights `networkidle`: Viele Shops halten dauerhaft
    Verbindungen offen — Chat-Widgets, Analytics-Beacons, Live-Suche. Dort
    tritt `networkidle` nie ein und man wartet den vollen Timeout ab.
    Hier genügt es, dass *neue* Requests aufhören.
    """
    deadline = time.monotonic() + timeout
    last_count = request_count()
    quiet_since = time.monotonic()

    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        current = request_count()
        if current != last_count:
            last_count = current
            quiet_since = time.monotonic()
        elif time.monotonic() - quiet_since >= quiet_for:
            return True
    return False


async def wait_for_host(
    hosts: Callable[[], set[str]],
    wanted: Iterable[str],
    timeout: float,
) -> str | None:
    """Wartet, bis ein Request an einen der gesuchten Hosts geht.

    Der schnellste Weg zum Ziel: Sobald `checkoutshopper-live.adyen.com`
    auftaucht, ist die Frage beantwortet und weiteres Warten sinnlos.
    """
    wanted_lower = [w.lower().lstrip("*.") for w in wanted]

    async def found() -> bool:
        return bool(_match(hosts(), wanted_lower))

    if await wait_until(found, timeout):
        return _match(hosts(), wanted_lower)
    return None


def _match(observed: set[str], wanted: list[str]) -> str | None:
    for host in observed:
        low = host.lower()
        for pattern in wanted:
            if low == pattern or low.endswith("." + pattern):
                return host
    return None


async def wait_for_text(page: Page, needles: Iterable[str], timeout: float, *, minimum: int = 1) -> bool:
    """Wartet, bis mindestens `minimum` der Begriffe im Seitentext stehen.

    Ersetzt das blinde Warten nach einem Seitenwechsel. Für die
    Zahlungsauswahl etwa reicht ein einzelner Begriff nicht — "Kreditkarte"
    steht auch im Footer. Zwei Treffer sind ein belastbarer Hinweis.
    """
    lowered = [n.lower() for n in needles]

    async def visible() -> bool:
        text = (await page.inner_text("body", timeout=2500)).lower()
        return sum(n in text for n in lowered) >= minimum

    return await wait_until(visible, timeout)


async def wait_for_selector_any(page: Page, selectors: Iterable[str], timeout: float) -> str | None:
    """Wartet, bis einer der Selektoren sichtbar ist, und gibt ihn zurück."""
    candidates = list(selectors)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        for selector in candidates:
            try:
                if await page.locator(selector).first.is_visible(timeout=250):
                    return selector
            except PlaywrightError:
                continue
        await asyncio.sleep(POLL_INTERVAL)
    return None


async def wait_for_url_change(page: Page, previous: str, timeout: float) -> bool:
    """Wartet auf einen Navigationswechsel, ohne an `goto` gebunden zu sein.

    Nötig, weil viele Shops den Checkout per JavaScript ansteuern — dann
    greifen die Navigationsereignisse von Playwright nicht zuverlässig.
    """

    async def changed() -> bool:
        return page.url.rstrip("/") != previous.rstrip("/")

    return await wait_until(changed, timeout)


async def wait_for_cart_change(page: Page, before: int, timeout: float = 8.0) -> bool:
    """Wartet, bis der Warenkorb mehr Artikel enthält als vorher.

    Die Erfolgskontrolle, die dem Vorgänger fehlte: Dort wurde geklickt und
    Erfolg angenommen. Schlug der Klick fehl — etwa weil eine Pflichtvariante
    nicht gewählt war —, lief die Simulation trotzdem weiter und meldete am
    Ende einen erreichten Checkout, den es nie gegeben hatte.
    """

    async def grown() -> bool:
        return await read_cart_count(page) > before

    return await wait_until(grown, timeout)


async def read_cart_count(page: Page) -> int:
    """Liest die Artikelzahl im Warenkorb, so gut es plattformneutral geht.

    Reihenfolge nach Verlässlichkeit: erst offizielle Shop-APIs, dann der
    im Markup ausgewiesene Zähler, dann sichtbare Ziffern in Warenkorb-Icons.
    Findet sich nichts, wird -1 zurückgegeben — nicht 0, damit "unbekannt"
    nicht mit "leer" verwechselt wird.
    """
    try:
        return await page.evaluate(
            """
            async () => {
              // Shopify: offizielle Cart-API
              try {
                const res = await fetch('/cart.js', {headers: {Accept: 'application/json'}});
                if (res.ok) { const c = await res.json(); if (typeof c.item_count === 'number') return c.item_count; }
              } catch (e) { /* kein Shopify */ }

              // Ausgewiesene Zähler im Markup
              const marker = document.querySelector(
                '[data-cart-count], [data-basket-count], [data-testid*="cart-count" i]'
              );
              if (marker) {
                const raw = marker.getAttribute('data-cart-count')
                         || marker.getAttribute('data-basket-count')
                         || marker.textContent;
                const n = parseInt(String(raw).replace(/\\D/g, ''), 10);
                if (!isNaN(n)) return n;
              }

              // Sichtbare Ziffer in einem Warenkorb-Element
              for (const el of document.querySelectorAll(
                '[class*="cart" i] [class*="count" i], [class*="basket" i] [class*="count" i],' +
                '[class*="cart" i] .badge, [aria-label*="Warenkorb" i]'
              )) {
                const n = parseInt((el.textContent || '').replace(/\\D/g, ''), 10);
                if (!isNaN(n)) return n;
              }
              return -1;
            }
            """
        )
    except PlaywrightError:
        return -1


async def settle(page: Page, request_count: Callable[[], int], *, budget: float = 6.0) -> None:
    """Lässt eine Seite zur Ruhe kommen — aber nur so lange wie nötig.

    Der Standardersatz für die früheren pauschalen `sleep`-Aufrufe nach
    einem Seitenwechsel. Ein Shop, der in 400 ms fertig ist, kostet auch
    nur 400 ms.
    """
    await wait_for_network_quiet(request_count, quiet_for=0.5, timeout=budget)
