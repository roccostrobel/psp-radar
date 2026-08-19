"""Shopware-Adapter (Version 5 und 6).

Im DACH-Mittelstand eines der wichtigsten Systeme — und eines der
lohnendsten, weil Shopware-Shops überdurchschnittlich oft mit deutschen
PSPs wie Unzer, Computop oder PAYONE arbeiten. Genau die Fälle, die
internationale Erkennungstools reihenweise übersehen.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from ...config import ScanConfig
from .base import CheckoutAdapter, fill_first


class ShopwareAdapter(CheckoutAdapter):
    platform_id = "shopware"
    name = "Shopware"

    CART_URLS = ("/checkout/cart", "/warenkorb")

    ADD_TO_CART = (
        "button.btn-buy",
        ".btn-buy",
        "button[title*='Warenkorb' i]",
        "form[action*='checkout/line-item/add'] button",
        "button:has-text('In den Warenkorb')",
        ".buybox--button",
    )

    TO_CHECKOUT = (
        "a[href*='checkout/confirm']",
        ".begin-checkout-btn",
        "a:has-text('Zur Kasse')",
        "button:has-text('Zur Kasse')",
        ".btn-checkout",
    )

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        """Shopware 6 nutzt /checkout/confirm, Shopware 5 /checkout/shippingPayment."""
        for path in ("/checkout/confirm", "/checkout/shippingPayment", "/checkout/register"):
            try:
                await page.goto(urljoin(base_url, path), wait_until="domcontentloaded", timeout=28000)
                await asyncio.sleep(2.5)
                body = (await page.inner_text("body", timeout=5000)).lower()
                if any(k in body for k in ("zahlungsart", "zahlungsmethode", "versandart", "anmelden")):
                    return True
            except PlaywrightError:
                continue
        return await super().go_to_checkout(page, base_url, config)

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Shopware verlangt Gast-Registrierung mit personal*/billingAddress*-Feldern."""
        # Gast-Bestellung aktivieren
        for selector in (
            "input#guest",
            "input[name='guest']",
            "label:has-text('Gastbestellung')",
            "a:has-text('Weiter als Gast')",
        ):
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1200):
                    await element.click(timeout=2500)
                    await asyncio.sleep(1.0)
                    break
            except PlaywrightError:
                continue

        filled = False
        filled |= await fill_first(
            page,
            ("input[name='email']", "input[name='personalMail']", "#personalMail"),
            config.dummy_email,
        )
        filled |= await fill_first(
            page,
            ("input[name='firstName']", "input[name='personalFirstname']", "#personalFirstName"),
            config.dummy_first_name,
        )
        filled |= await fill_first(
            page,
            ("input[name='lastName']", "input[name='personalLastname']", "#personalLastName"),
            config.dummy_last_name,
        )
        filled |= await fill_first(
            page,
            ("input[name='billingAddress[street]']", "input[name='register[billing][street]']", "#billingAddressAddressStreet"),
            config.dummy_street,
        )
        filled |= await fill_first(
            page,
            ("input[name='billingAddress[zipcode]']", "input[name='register[billing][zipcode]']", "#billingAddressAddressZipcode"),
            config.dummy_zip,
        )
        filled |= await fill_first(
            page,
            ("input[name='billingAddress[city]']", "input[name='register[billing][city]']", "#billingAddressAddressCity"),
            config.dummy_city,
        )
        await asyncio.sleep(2.0)
        return filled
