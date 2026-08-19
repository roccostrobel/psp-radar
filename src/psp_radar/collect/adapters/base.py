"""Basis für Checkout-Adapter.

Jeder Shop ist anders gebaut, aber der Ablauf ist überall derselbe:
Produkt öffnen → in den Warenkorb → zum Checkout → Adresse ausfüllen →
Zahlungsauswahl. Diese Klasse implementiert den Ablauf generisch mit
robusten Heuristiken; Plattform-Adapter überschreiben nur, was ihr System
anders macht.

Sicherheitsregel, die für alle Adapter gilt und nicht umgangen werden darf:
**Es wird nie eine Bestellung ausgelöst.** Vor jedem Klick wird der
Beschriftungstext gegen eine Sperrliste geprüft. Ziel ist die Seite mit der
Zahlungsauswahl — dort ist Schluss.
"""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from ...config import FORBIDDEN_SUBMIT_PATTERNS, ScanConfig

_FORBIDDEN = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_SUBMIT_PATTERNS)


def is_forbidden_label(text: str) -> bool:
    """Ob ein Beschriftungstext auf einen kaufauslösenden Button hindeutet."""
    return any(rx.search(text) for rx in _FORBIDDEN)


async def safe_click(locator: Locator, timeout: float = 5.0) -> bool:
    """Klickt ein Element — aber nur, wenn es garantiert nichts bestellt.

    Der Text des Elements wird vorher gelesen und gegen die Sperrliste
    geprüft. Lässt sich der Text nicht ermitteln, wird nicht geklickt.
    Im Zweifel lieber ein verpasstes Signal als eine ausgelöste Bestellung.
    """
    try:
        if not await locator.is_visible(timeout=timeout * 1000):
            return False

        label = " ".join(
            filter(
                None,
                [
                    (await locator.inner_text(timeout=2000) or "").strip(),
                    await locator.get_attribute("value") or "",
                    await locator.get_attribute("aria-label") or "",
                    await locator.get_attribute("title") or "",
                ],
            )
        )
    except PlaywrightError:
        return False

    if is_forbidden_label(label):
        return False

    try:
        await locator.click(timeout=timeout * 1000)
        return True
    except PlaywrightError:
        return False


async def try_selectors(page: Page, selectors: tuple[str, ...], timeout: float = 3.0) -> bool:
    """Probiert Selektoren der Reihe nach und klickt den ersten passenden."""
    for selector in selectors:
        try:
            if await safe_click(page.locator(selector).first, timeout=timeout):
                return True
        except PlaywrightError:
            continue
    return False


async def fill_first(page: Page, selectors: tuple[str, ...], value: str) -> bool:
    """Füllt das erste sichtbare Feld aus der Selektorliste."""
    for selector in selectors:
        try:
            field = page.locator(selector).first
            if await field.is_visible(timeout=1200):
                await field.fill(value, timeout=3000)
                return True
        except PlaywrightError:
            continue
    return False


class CheckoutAdapter:
    """Generischer Adapter — greift, wenn keine Plattform erkannt wurde."""

    #: Plattform-ID aus platforms.yaml, für die dieser Adapter zuständig ist
    platform_id: str | None = None
    name: str = "generisch"

    #: Reihenfolge nach Verlässlichkeit. Ganz oben stehen Attribute, die
    #: Shops für ihre eigenen automatisierten Tests vergeben — die sind
    #: deutlich stabiler als CSS-Klassen, weil sie einen Umbau des Designs
    #: überleben. Bei bergfreunde.de etwa `data-codecept="toBasket"`, was
    #: keiner der klassenbasierten Selektoren gefunden hätte.
    ADD_TO_CART = (
        "[data-codecept*='toBasket' i]",
        "[data-testid*='add-to-cart' i]",
        "[data-testid*='addtocart' i]",
        "[data-test*='add-to-cart' i]",
        "[id*='addToCart' i]",
        "[id*='toBasket' i]",
        "button[name='add']",
        "button[name='tobasket']",
        "form[action*='cart'] button[type='submit']",
        "button[aria-label*='Warenkorb' i]",
        "button:has-text('In den Warenkorb')",
        "button:has-text('In den Einkaufswagen')",
        "button:has-text('Zum Warenkorb hinzufügen')",
        "button:has-text('Add to cart')",
        "button:has-text('Add to bag')",
        "a:has-text('In den Warenkorb')",
        "[class*='add-to-cart'] button",
        "button[class*='addtocart' i]",
        "input[value*='Warenkorb' i]",
    )

    CART_URLS = ("/cart", "/warenkorb", "/checkout/cart", "/basket")

    TO_CHECKOUT = (
        "a[href*='checkout']:visible",
        "button:has-text('Zur Kasse')",
        "a:has-text('Zur Kasse')",
        "button:has-text('Weiter zur Kasse')",
        "button:has-text('Checkout')",
        "a:has-text('Checkout')",
        "button:has-text('Zur Bestellung')",
        "[data-testid*='checkout']",
    )

    GUEST_CHECKOUT = (
        "button:has-text('Als Gast')",
        "a:has-text('Als Gast')",
        "label:has-text('Als Gast bestellen')",
        "input[value='guest']",
        "button:has-text('Ohne Konto')",
        "button:has-text('Continue as guest')",
    )

    EMAIL = ("input[type='email']", "input[name*='email' i]", "#email")
    FIRST_NAME = ("input[name*='firstname' i]", "input[name*='first_name' i]", "input[id*='firstName' i]")
    LAST_NAME = ("input[name*='lastname' i]", "input[name*='last_name' i]", "input[id*='lastName' i]")
    STREET = ("input[name*='street' i]", "input[name*='address1' i]", "input[name*='address' i]")
    ZIP = ("input[name*='zip' i]", "input[name*='postal' i]", "input[name*='plz' i]")
    CITY = ("input[name*='city' i]", "input[name*='ort' i]")

    CONTINUE = (
        "button:has-text('Weiter'):not(:has-text('bestellen'))",
        "button:has-text('Weiter zur Zahlung')",
        "button:has-text('Zur Zahlungsart')",
        "button:has-text('Continue to payment')",
        "button:has-text('Continue to shipping')",
        "button[type='submit']:not([name*='order'])",
    )

    #: Woran erkennen wir, dass die Zahlungsauswahl erreicht ist?
    PAYMENT_MARKERS = (
        "kreditkarte",
        "zahlungsart",
        "zahlungsmethode",
        "zahlungsweise",
        "payment method",
        "rechnungskauf",
        "sepa-lastschrift",
        "vorkasse",
        "zahlungsoptionen",
    )

    # ------------------------------------------------------------------

    async def add_to_cart(self, page: Page, config: ScanConfig) -> bool:
        """Legt das aktuell geöffnete Produkt in den Warenkorb."""
        await self._select_required_variants(page)
        clicked = await try_selectors(page, self.ADD_TO_CART, timeout=4.0)
        if clicked:
            await asyncio.sleep(2.5)  # Warenkorb-Drawer / AJAX abwarten
        return clicked

    async def _select_required_variants(self, page: Page) -> None:
        """Wählt Pflichtvarianten (Grösse, Farbe) vor, sonst blockt der Button.

        Bei Bekleidungsshops die häufigste Ursache dafür, dass "In den
        Warenkorb" nichts tut.
        """
        try:
            selects = page.locator("select[required], form select")
            count = min(await selects.count(), 4)
            for index in range(count):
                select = selects.nth(index)
                if not await select.is_visible(timeout=800):
                    continue
                options = await select.locator("option").all()
                for option in options[1:]:
                    value = await option.get_attribute("value")
                    disabled = await option.get_attribute("disabled")
                    if value and disabled is None:
                        await select.select_option(value, timeout=2500)
                        break
        except PlaywrightError:
            pass

        # Varianten-Buttons (Grössen als Kacheln)
        for selector in (
            "[class*='variant'] button:not([disabled])",
            "[class*='swatch'] input:not([disabled])",
            "fieldset label:not([class*='disabled'])",
        ):
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=800):
                    await element.click(timeout=2000)
                    await asyncio.sleep(0.6)
                    break
            except PlaywrightError:
                continue

    async def go_to_cart(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        from urllib.parse import urljoin

        for path in self.CART_URLS:
            try:
                await page.goto(urljoin(base_url, path), wait_until="domcontentloaded", timeout=25000)
                text = (await page.inner_text("body", timeout=5000)).lower()
                if any(k in text for k in ("warenkorb", "cart", "basket", "kasse")) and not any(
                    k in text for k in ("leer", "empty")
                ):
                    return True
            except PlaywrightError:
                continue
        return False

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        if await try_selectors(page, self.TO_CHECKOUT, timeout=4.0):
            await asyncio.sleep(3.0)
            return True

        from urllib.parse import urljoin

        for path in ("/checkout", "/kasse", "/checkout/onepage", "/checkout/confirm"):
            try:
                await page.goto(urljoin(base_url, path), wait_until="domcontentloaded", timeout=25000)
                if "checkout" in page.url.lower() or "kasse" in page.url.lower():
                    await asyncio.sleep(2.0)
                    return True
            except PlaywrightError:
                continue
        return False

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Füllt einen Gast-Checkout mit erkennbar synthetischen Testdaten."""
        await try_selectors(page, self.GUEST_CHECKOUT, timeout=2.5)
        await asyncio.sleep(1.0)

        filled = False
        filled |= await fill_first(page, self.EMAIL, config.dummy_email)
        filled |= await fill_first(page, self.FIRST_NAME, config.dummy_first_name)
        filled |= await fill_first(page, self.LAST_NAME, config.dummy_last_name)
        filled |= await fill_first(page, self.STREET, config.dummy_street)
        filled |= await fill_first(page, self.ZIP, config.dummy_zip)
        filled |= await fill_first(page, self.CITY, config.dummy_city)
        return filled

    async def advance(self, page: Page, config: ScanConfig, steps: int = 3) -> None:
        """Klickt sich Richtung Zahlungsauswahl vor — nie darüber hinaus."""
        for _ in range(steps):
            if await self.at_payment_selection(page):
                return
            if not await try_selectors(page, self.CONTINUE, timeout=3.0):
                return
            await asyncio.sleep(3.0)

    async def at_payment_selection(self, page: Page) -> bool:
        """Prüft, ob die Zahlungsauswahl sichtbar ist."""
        try:
            text = (await page.inner_text("body", timeout=5000)).lower()
        except PlaywrightError:
            return False
        return sum(marker in text for marker in self.PAYMENT_MARKERS) >= 2
