"""Shopify-Adapter.

Shopify ist der dankbarste Fall: Die Struktur ist über alle Shops hinweg
identisch, `/cart/add.js` funktioniert überall, und die Varianten-ID lässt
sich zuverlässig aus `/products.json` holen. Kein Raten nötig.
"""

from __future__ import annotations

import json
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ...config import ScanConfig
from ..waiting import read_cart_count, wait_for_text, wait_until
from .base import CheckoutAdapter, safe_goto


class ShopifyAdapter(CheckoutAdapter):
    platform_id = "shopify"
    name = "Shopify"

    CART_URLS = ("/cart",)

    TO_CHECKOUT = (
        "button[name='checkout']",
        "input[name='checkout']",
        "a[href='/checkout']",
        "button:has-text('Zur Kasse')",
        "button:has-text('Checkout')",
    )

    async def add_to_cart(self, page: Page, config: ScanConfig) -> bool:
        """Legt direkt über die Cart-API an — deutlich verlässlicher als Klicken."""
        if await self._add_via_api(page):
            return True
        return await super().add_to_cart(page, config)

    async def _add_via_api(self, page: Page) -> bool:
        """Holt eine lieferbare Varianten-ID und postet sie an /cart/add.js."""
        try:
            variant_id = await page.evaluate(
                """
                async () => {
                  // Variante aus dem eingebetteten Produkt-JSON ziehen
                  const handle = window.location.pathname.split('/products/')[1]?.split('?')[0];
                  if (!handle) return null;
                  const res = await fetch(`/products/${handle}.js`, {headers: {'Accept': 'application/json'}});
                  if (!res.ok) return null;
                  const product = await res.json();
                  const available = (product.variants || []).find(v => v.available);
                  return (available || product.variants?.[0])?.id ?? null;
                }
                """
            )
            if not variant_id:
                return False

            result = await page.evaluate(
                """
                async (id) => {
                  const res = await fetch('/cart/add.js', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({items: [{id: id, quantity: 1}]})
                  });
                  return res.ok;
                }
                """,
                variant_id,
            )
            if result:
                # Die Cart-API meldet Erfolg selbst; trotzdem gegenprüfen,
                # denn ein 200 auf /cart/add.js heisst nicht zwingend, dass
                # der Artikel lieferbar war.
                return await wait_until(lambda: self._im_warenkorb(page), timeout=8.0)
        except PlaywrightError:
            pass
        return False

    async def _im_warenkorb(self, page: Page) -> bool:
        return await read_cart_count(page) > 0

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        """Shopify hat einen festen Checkout-Pfad."""
        if not await safe_goto(page, urljoin(base_url, "/checkout"), timeout=30.0):
            return await super().go_to_checkout(page, base_url, config)
        if "checkout" not in page.url.lower():
            return await super().go_to_checkout(page, base_url, config)
        # Shopifys Checkout rendert clientseitig — auf Inhalt warten, nicht
        # auf eine Sekundenzahl. Unter Last (zwei Chromium-Instanzen
        # gleichzeitig) waren die früheren 3,5 s regelmässig zu kurz, und
        # genau daran scheiterte snocks.com über die Oberfläche, während es
        # über die Kommandozeile im selben Durchlauf funktionierte.
        await wait_for_text(
            page,
            (*self.PAYMENT_MARKERS, "kontakt", "lieferung", "e-mail", "versand"),
            timeout=20.0,
        )
        return True

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Shopifys Checkout nutzt eigene Feldnamen."""
        from .base import fill_first

        filled = False
        filled |= await fill_first(
            page, ("input[name='email']", "#email", "input[type='email']"), config.dummy_email
        )
        filled |= await fill_first(
            page, ("input[name='firstName']", "#TextField0"), config.dummy_first_name
        )
        filled |= await fill_first(page, ("input[name='lastName']",), config.dummy_last_name)
        filled |= await fill_first(page, ("input[name='address1']",), config.dummy_street)
        filled |= await fill_first(page, ("input[name='postalCode']",), config.dummy_zip)
        filled |= await fill_first(page, ("input[name='city']",), config.dummy_city)
        return filled

    @staticmethod
    async def first_product_url(page: Page, base_url: str) -> str | None:
        """Zieht eine Produkt-URL aus /products.json — ohne Crawling."""
        try:
            response = await page.request.get(urljoin(base_url, "/products.json?limit=10"))
            if not response.ok:
                return None
            data = json.loads(await response.text())
            for product in data.get("products", []):
                if any(v.get("available") for v in product.get("variants", [])):
                    return urljoin(base_url, f"/products/{product['handle']}")
            products = data.get("products", [])
            if products:
                return urljoin(base_url, f"/products/{products[0]['handle']}")
        except (PlaywrightError, json.JSONDecodeError, KeyError):
            return None
        return None
