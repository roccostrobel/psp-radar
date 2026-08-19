"""Stufe 2 — echtes Rendering im Browser.

Was hier dazukommt, ist alles, was der statische Abruf prinzipbedingt nicht
sehen kann: per JavaScript nachgeladene SDKs, dynamisch eingehängte iframes,
Cookies, die erst ein Skript setzt. Eine Produktseite wird bewusst
mitbesucht — dort binden viele Shops ihre BNPL-Widgets ein
("ab 12 € / Monat mit Klarna"), und die verraten den Anbieter direkt.
"""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page
from playwright.async_api import Error as PlaywrightError

from ..config import ScanConfig
from ..core.models import ScanWarning, Stage
from ..core.observation import Observation
from .browser import Recorder, snapshot
from .normalize import NormalizeResult

#: Linktexte/Pfade, die typischerweise auf eine Produktdetailseite führen
PRODUCT_HINTS = (
    "/products/",
    "/produkt/",
    "/produkte/",
    "/artikel/",
    "/p/",
    "/detail/",
    "/shop/",
    "/item/",
)


async def _goto(page: Page, url: str, timeout: float) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        # Kurz nachlaufen lassen: PSP-Skripte laden oft verzögert
        with contextlib.suppress(PlaywrightError):
            await page.wait_for_load_state("networkidle", timeout=8000)
        return True
    except PlaywrightError:
        return False


async def find_product_url(page: Page, base_url: str) -> str | None:
    """Sucht eine plausible Produktseite auf der aktuellen Seite.

    Mehrstufig, weil kein Shop wie der andere aussieht: erst
    strukturierte Daten (verlässlich), dann typische URL-Muster,
    dann Links mit Preisangabe in der Nähe.
    """
    # 1. JSON-LD — wenn vorhanden, die sauberste Quelle
    try:
        product_url: str | None = await page.evaluate(
            """
            () => {
              const nodes = document.querySelectorAll('script[type="application/ld+json"]');
              for (const n of nodes) {
                try {
                  const parsed = JSON.parse(n.textContent);
                  const items = Array.isArray(parsed) ? parsed : [parsed];
                  for (const item of items) {
                    const graph = item['@graph'] || [item];
                    for (const g of graph) {
                      if (g['@type'] === 'Product' && g.url) return g.url;
                      if (g['@type'] === 'ItemList' && g.itemListElement?.length) {
                        const first = g.itemListElement[0];
                        if (first.url) return first.url;
                        if (first.item?.url) return first.item.url;
                      }
                    }
                  }
                } catch (e) { /* kaputtes JSON-LD ignorieren */ }
              }
              return null;
            }
            """
        )
        if product_url:
            return urljoin(base_url, product_url)
    except PlaywrightError:
        pass

    # 2. URL-Muster
    try:
        hrefs: list[str] = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href).slice(0, 400)"
        )
    except PlaywrightError:
        return None

    host = urlparse(base_url).hostname or ""
    internal = [h for h in hrefs if urlparse(h).hostname == host]

    for hint in PRODUCT_HINTS:
        for href in internal:
            path = urlparse(href).path
            # Ein echter Produktlink hat nach dem Muster noch einen Slug
            if hint in path and len(path.rstrip("/").split(hint)[-1]) > 2:
                return href

    return None


async def collect_rendered(
    context: BrowserContext,
    recorder: Recorder,
    normalized: NormalizeResult,
    config: ScanConfig,
) -> tuple[list[Observation], list[ScanWarning], str | None]:
    """Rendert Startseite und eine Produktseite.

    Gibt zusätzlich die gefundene Produkt-URL zurück — Stufe 3 baut darauf auf,
    statt die Suche zu wiederholen.
    """
    observations: list[Observation] = []
    warnings: list[ScanWarning] = []
    product_url: str | None = None

    page = await context.new_page()
    try:
        if not await _goto(page, normalized.final_url, config.page_timeout):
            warnings.append(
                ScanWarning(
                    code="render_home_failed",
                    message="Startseite konnte im Browser nicht geladen werden",
                    stage=Stage.RENDER,
                )
            )
            return observations, warnings, None

        observations.append(await snapshot(page, recorder, Stage.RENDER))

        # Cookie-Banner wegklicken — dahinter laden manche Shops erst
        # ihre Zahlungs-Widgets nach.
        await _dismiss_cookie_banner(page)
        await asyncio.sleep(1.0)

        product_url = await find_product_url(page, normalized.final_url)
        if product_url is None:
            warnings.append(
                ScanWarning(
                    code="no_product_found",
                    message="Keine Produktseite gefunden — Erkennung stützt sich auf Startseite",
                    stage=Stage.RENDER,
                )
            )
            return observations, warnings, None

        await asyncio.sleep(config.delay_between_requests)
        mark = len(recorder.urls)

        if await _goto(page, product_url, config.page_timeout):
            await asyncio.sleep(1.5)  # BNPL-Widgets laden verzögert
            observations.append(await snapshot(page, recorder, Stage.RENDER, since=mark))
        else:
            warnings.append(
                ScanWarning(
                    code="render_product_failed",
                    message=f"Produktseite nicht ladbar: {product_url}",
                    stage=Stage.RENDER,
                )
            )
    finally:
        await page.close()

    return observations, warnings, product_url


async def _dismiss_cookie_banner(page: Page) -> None:
    """Versucht, einen Consent-Dialog zu schliessen.

    Bewusst nur Zustimmen-Buttons: Ablehnen würde in vielen Shops genau die
    Skripte blockieren, die wir sehen wollen. Es werden keine Daten
    übermittelt, die über einen normalen Seitenbesuch hinausgehen.
    """
    selectors = (
        "#onetrust-accept-btn-handler",
        "button#uc-btn-accept-banner",
        "[data-testid='uc-accept-all-button']",
        "button[aria-label*='akzeptieren' i]",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Alle Cookies akzeptieren')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Zustimmen')",
        "button:has-text('Einverstanden')",
        "button:has-text('Accept all')",
        ".cmplz-accept",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    )

    for selector in selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=1200):
                await element.click(timeout=2500)
                await asyncio.sleep(0.8)
                return
        except PlaywrightError:
            continue
