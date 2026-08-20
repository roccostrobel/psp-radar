"""WooCommerce-Adapter.

WooCommerce ist im DACH-Raum extrem verbreitet und gleichzeitig der
unberechenbarste Fall: Jedes Theme bringt eigenes Markup mit. Verlässlich
sind nur die Kernklassen von Woo selbst (`.single_add_to_cart_button`,
`?add-to-cart=<id>`) — auf die stützt sich dieser Adapter.
"""

from __future__ import annotations

from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ...config import ScanConfig
from ..waiting import read_cart_count, wait_for_text
from .base import CheckoutAdapter, fill_first, safe_goto


class WooCommerceAdapter(CheckoutAdapter):
    platform_id = "woocommerce"
    name = "WooCommerce"

    CART_URLS = ("/cart", "/warenkorb", "/?page_id=cart")

    ADD_TO_CART = (
        "button.single_add_to_cart_button",
        "button[name='add-to-cart']",
        ".single_add_to_cart_button",
        "a.add_to_cart_button",
        "button:has-text('In den Warenkorb')",
    )

    TO_CHECKOUT = (
        "a.checkout-button",
        ".wc-proceed-to-checkout a",
        "a[href*='checkout']",
        "button:has-text('Weiter zur Kasse')",
    )

    async def add_to_cart(self, page: Page, config: ScanConfig) -> bool:
        """Nutzt den add-to-cart-Query-Parameter als robusten Fallback."""
        if await super().add_to_cart(page, config):
            return True

        vorher = await read_cart_count(page)

        # Produkt-ID aus dem Markup ziehen und per URL anlegen
        try:
            product_id = await page.evaluate(
                """
                () => {
                  const el = document.querySelector('[name="add-to-cart"], [data-product_id], .post-.product');
                  if (el?.value) return el.value;
                  if (el?.dataset?.product_id) return el.dataset.product_id;
                  const body = document.body.className.match(/postid-(\\d+)/);
                  return body ? body[1] : null;
                }
                """
            )
            if product_id:
                ziel = f"{page.url.split('?')[0]}?add-to-cart={product_id}"
                if await safe_goto(page, ziel, timeout=25.0):
                    return await self.cart_grew(page, vorher)
        except PlaywrightError:
            pass
        return False

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        for path in ("/checkout", "/kasse", "/?page_id=checkout"):
            if not await safe_goto(page, urljoin(base_url, path), timeout=25.0):
                continue
            if await wait_for_text(page, ("rechnungsdetails", "billing", "zahlung"), timeout=8.0):
                return True
        return await super().go_to_checkout(page, base_url, config)

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Woo nutzt durchgängig das billing_*-Namensschema."""
        filled = False
        filled |= await fill_first(page, ("#billing_email", "input[name='billing_email']"), config.dummy_email)
        filled |= await fill_first(page, ("#billing_first_name",), config.dummy_first_name)
        filled |= await fill_first(page, ("#billing_last_name",), config.dummy_last_name)
        filled |= await fill_first(page, ("#billing_address_1",), config.dummy_street)
        filled |= await fill_first(page, ("#billing_postcode",), config.dummy_zip)
        filled |= await fill_first(page, ("#billing_city",), config.dummy_city)
        filled |= await fill_first(page, ("#billing_phone",), config.dummy_phone)

        # Woo lädt die Zahlungsarten per AJAX neu, sobald das Land steht.
        # Darauf lässt sich warten — der Block trägt eine feste ID.
        await wait_for_text(page, self.PAYMENT_MARKERS, timeout=12.0, minimum=2)
        return filled
