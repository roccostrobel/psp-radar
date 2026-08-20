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

from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ...config import ScanConfig
from ..waiting import (
    read_cart_count,
    wait_for_selector_any,
    wait_for_text,
    wait_for_url_change,
    wait_until,
)
from .base import CheckoutAdapter, fill_first, safe_click, safe_goto, try_selectors


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
        """Erst Varianten wählen, dann kaufen, dann die Zwischenschicht wegklicken.

        Der Rückgabewert war früher immer `True`, sobald der Klick abgesetzt
        war. Genau das machte bergfreunde.de zu einem stillen Fehlschlag: Die
        Kachel-Variante war nicht gewählt, der Button blieb wirkungslos, und
        die Simulation lief bis zur Meldung "Checkout erreicht" weiter.
        """
        vorher = await read_cart_count(page)
        await self._select_tile_variants(page)

        if not await try_selectors(page, self.ADD_TO_CART, timeout=4.0):
            return False

        # Bestätigungsschicht überspringen, falls vorhanden. Ob sie erscheint,
        # ist je nach Theme unterschiedlich — deshalb kein harter Fehler.
        await try_selectors(page, self.AFTER_ADD, timeout=3.0)
        return await self.cart_grew(page, vorher)

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
                            await self._warte_auf_freigabe(page)
                            break
        except PlaywrightError:
            pass

        if await self._button_frei(page):
            return

        # Dann Kachel-Varianten. Die ersten beiden Muster sind Shop-eigene
        # Testanker und Zugänglichkeitsattribute — sie überleben einen
        # Designumbau, Klassennamen nicht. Bei bergfreunde.de führte genau
        # diese Reihenfolge zum Ziel, während `.variants a` ins Leere lief:
        # das Frontend ist mit Tailwind gebaut und hat keine sprechenden
        # Klassen mehr.
        tile_selectors = (
            "[data-codecept*='variant' i]:not([disabled])",
            "[data-testid*='variant' i]:not([disabled])",
            "[role='radio']:not([aria-disabled='true']):not([disabled])",
            "label:has(input[type='radio']:not([disabled]))",
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
                    if any(
                        k in text
                        for k in ("ausverkauft", "nicht verfügbar", "nicht lieferbar", "sold out")
                    ):
                        continue
                    if await safe_click(tile, timeout=2.5):
                        await self._warte_auf_freigabe(page)
                        if await self._button_frei(page):
                            return
            except PlaywrightError:
                continue

    async def _warte_auf_freigabe(self, page: Page) -> None:
        """Wartet, bis der Warenkorb-Button freigegeben ist.

        Ersetzt die früheren `sleep(1.2)` und `sleep(1.5)`. OXID-Shops laden
        nach der Variantenwahl die Verfügbarkeit per AJAX nach; wie lange das
        dauert, weiss man vorher nicht. Ein fester Wert war für schnelle
        Shops Verschwendung und für langsame zu kurz — und zu kurz heisst
        hier: Klick auf einen noch gesperrten Button, also stiller Fehlschlag.
        """
        await wait_until(lambda: self._button_frei(page), timeout=6.0)

    #: Marken der OXID-Kundenseite — der Schritt vor der Zahlungsauswahl
    KUNDENSEITE = ("gastbestellung", "als gast", "rechnungsadresse", "anmelden")

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        vorher = page.url
        if await try_selectors(page, self.TO_CHECKOUT, timeout=4.0) and (
            await wait_for_url_change(page, vorher, timeout=12.0)
            or await wait_for_text(page, self.KUNDENSEITE, timeout=8.0)
        ):
            return True

        for path in ("/kunde/", "/?cl=user", "/index.php?cl=user"):
            if not await safe_goto(page, urljoin(base_url, path), timeout=28.0):
                continue
            if await wait_for_text(page, self.KUNDENSEITE, timeout=8.0):
                return True
        return False

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Gast-Bestellung wählen und die Rechnungsadresse ausfüllen."""
        if await try_selectors(page, self.GUEST_CHECKOUT, timeout=3.0):
            await wait_for_selector_any(
                page,
                ("input[name*='oxfname' i]", "input[name*='lgn_usr' i]", "input[type='email']"),
                timeout=8.0,
            )

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
        return filled
