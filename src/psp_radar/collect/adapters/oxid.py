"""OXID-eShop-Adapter.

Entstanden aus einem konkreten Fehlschlag: bergfreunde.de wurde als OXID zu
97 % erkannt, aber der generische Adapter bekam das Produkt nicht in den
Warenkorb — und ohne Warenkorb kein Checkout, ohne Checkout kein PSP.

Beim manuellen Nachstellen im Browser zeigte sich die Ursache. OXID-Shops
mit Grössenvarianten rendern die Auswahl als Kachel-Links, nicht als
`<select>` und nicht als `<button>`. Der generische Adapter suchte nach
beidem und fand nichts, der Kaufen-Button blieb wirkungslos.

Zweite Beobachtung: Nach dem Hinzufügen erscheint eine Zwischenschicht
("Du hast das folgende Produkt in den Warenkorb gelegt") mit einem
separaten Weiter-Button. Wer die übersieht, landet nie im Warenkorb.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ...config import ScanConfig
from .base import CheckoutAdapter, fill_first, safe_click, try_selectors


class OxidAdapter(CheckoutAdapter):
    platform_id = "oxid"
    name = "OXID eShop"

    #: OXID steuert klassisch über den cl-Parameter, moderne Shops nutzen
    #: sprechende Pfade. Beide Varianten werden probiert.
    CART_URLS = ("/warenkorb/", "/?cl=basket", "/index.php?cl=basket", "/basket/")

    ADD_TO_CART = (
        "#toBasket",
        "button[name='tobasket']",
        "form[name='tobasket'] button[type='submit']",
        ".btn-buy",
        "button:has-text('In den Warenkorb')",
        "a:has-text('In den Warenkorb')",
        "input[value*='Warenkorb' i]",
    )

    #: Zwischenschicht nach dem Hinzufügen
    AFTER_ADD = (
        "a:has-text('Zum Warenkorb')",
        "button:has-text('Zum Warenkorb')",
        ".btn-basket",
    )

    TO_CHECKOUT = (
        "a:has-text('Zur Kasse gehen')",
        "button:has-text('Zur Kasse gehen')",
        "a[href*='cl=user']",
        "a:has-text('Zur Kasse')",
        ".btn-checkout",
    )

    GUEST_CHECKOUT = (
        "a:has-text('Als Gast bestellen')",
        "button:has-text('Als Gast bestellen')",
        "a[href*='cl=user'][href*='guest']",
        "button:has-text('Ohne Anmeldung')",
    )

    CONTINUE = (
        "button:has-text('Weiter zur Zahlungsart')",
        "a:has-text('Weiter zur Zahlungsart')",
        "button:has-text('Weiter zum Versand')",
        "button:has-text('Weiter'):not(:has-text('bestell'))",
    )

    async def add_to_cart(self, page: Page, config: ScanConfig) -> bool:
        """Erst Varianten wählen, dann kaufen, dann die Zwischenschicht wegklicken."""
        await self._select_tile_variants(page)
        await asyncio.sleep(1.0)

        if not await try_selectors(page, self.ADD_TO_CART, timeout=4.0):
            return False

        await asyncio.sleep(2.5)
        # Bestätigungsschicht überspringen, falls vorhanden. Ob sie erscheint,
        # ist je nach Theme unterschiedlich — deshalb kein harter Fehler.
        await try_selectors(page, self.AFTER_ADD, timeout=3.0)
        await asyncio.sleep(1.5)
        return True

    async def _select_tile_variants(self, page: Page) -> None:
        """Wählt Varianten, die als anklickbare Kacheln umgesetzt sind.

        Genau der Fall, an dem der generische Adapter scheiterte: Grössen
        wie "30 m" oder "42" stehen in Links oder Listenelementen, nicht in
        einem `<select>`. Ausgeschlossen werden ausdrücklich als nicht
        lieferbar markierte Kacheln — sonst wählt man eine Variante, die
        den Kaufen-Button erst recht blockiert.
        """
        # Zuerst der Normalfall: klassische OXID-Auswahllisten
        try:
            for selector in ("select[name^='varselid']", ".varselect select", "form select"):
                boxes = page.locator(selector)
                for index in range(min(await boxes.count(), 3)):
                    box = boxes.nth(index)
                    if not await box.is_visible(timeout=800):
                        continue
                    options = await box.locator("option").all()
                    for option in options[1:]:
                        value = await option.get_attribute("value")
                        if value and await option.get_attribute("disabled") is None:
                            await box.select_option(value, timeout=2500)
                            await asyncio.sleep(1.2)
                            break
        except PlaywrightError:
            pass

        # Dann Kachel-Varianten
        tile_selectors = (
            ".variants a:not([class*='disabled']):not([class*='soldout'])",
            "[class*='variant'] li:not([class*='disabled']) a",
            "[class*='size'] a:not([class*='disabled'])",
            "[class*='selector'] li:not([class*='disabled'])",
            "[data-variant]:not([disabled])",
        )
        for selector in tile_selectors:
            try:
                tiles = page.locator(selector)
                count = await tiles.count()
                if not count:
                    continue
                for index in range(min(count, 8)):
                    tile = tiles.nth(index)
                    if not await tile.is_visible(timeout=600):
                        continue
                    text = (await tile.inner_text(timeout=1000) or "").lower()
                    if any(k in text for k in ("ausverkauft", "nicht verfügbar", "sold out")):
                        continue
                    if await safe_click(tile, timeout=2.5):
                        await asyncio.sleep(1.5)
                        return
            except PlaywrightError:
                continue

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        if await try_selectors(page, self.TO_CHECKOUT, timeout=4.0):
            await asyncio.sleep(3.0)
            return True

        for path in ("/kunde/", "/?cl=user", "/index.php?cl=user"):
            try:
                await page.goto(urljoin(base_url, path), wait_until="domcontentloaded", timeout=28000)
                await asyncio.sleep(2.5)
                body = (await page.inner_text("body", timeout=5000)).lower()
                if any(k in body for k in ("gastbestellung", "als gast", "rechnungsadresse", "anmelden")):
                    return True
            except PlaywrightError:
                continue
        return False

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Gast-Bestellung wählen und die Rechnungsadresse ausfüllen."""
        await try_selectors(page, self.GUEST_CHECKOUT, timeout=3.0)
        await asyncio.sleep(2.5)

        filled = False
        filled |= await fill_first(
            page,
            ("input[name*='lgn_usr' i]", "input[type='email']", "input[name*='email' i]"),
            config.dummy_email,
        )
        filled |= await fill_first(
            page,
            ("input[name*='oxfname' i]", "input[name*='firstname' i]", "input[name*='vorname' i]"),
            config.dummy_first_name,
        )
        filled |= await fill_first(
            page,
            ("input[name*='oxlname' i]", "input[name*='lastname' i]", "input[name*='nachname' i]"),
            config.dummy_last_name,
        )
        filled |= await fill_first(
            page, ("input[name*='oxstreet' i]", "input[name*='street' i]"), config.dummy_street
        )
        filled |= await fill_first(
            page, ("input[name*='oxstreetnr' i]", "input[name*='nr' i]"), "1"
        )
        filled |= await fill_first(
            page, ("input[name*='oxzip' i]", "input[name*='zip' i]", "input[name*='plz' i]"), config.dummy_zip
        )
        filled |= await fill_first(
            page, ("input[name*='oxcity' i]", "input[name*='city' i]", "input[name*='ort' i]"), config.dummy_city
        )

        await asyncio.sleep(2.0)
        return filled
