"""Shopware-Adapter (Version 5 und 6).

Im DACH-Mittelstand eines der wichtigsten Systeme — und eines der
lohnendsten, weil Shopware-Shops überdurchschnittlich oft mit deutschen
PSPs wie Unzer, Computop oder PAYONE arbeiten. Genau die Fälle, die
internationale Erkennungstools reihenweise übersehen.
"""

from __future__ import annotations

from urllib.parse import urljoin

from playwright.async_api import Page

from ...config import ScanConfig
from ..waiting import wait_for_selector_any, wait_for_text
from .base import CheckoutAdapter, fill_first, safe_goto, try_selectors


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

    #: Shopware nennt die Gast-Option je nach Version anders
    GUEST_CHECKOUT = (
        "input#guest",
        "input[name='guest']",
        "label:has-text('Gastbestellung')",
        "a:has-text('Weiter als Gast')",
    )

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        """Shopware 6 nutzt /checkout/confirm, Shopware 5 /checkout/shippingPayment.

        `/checkout/confirm` ist die Übersichtsseite, auf der auch der
        Kaufbutton steht. Sie zu **öffnen** ist unbedenklich — sie zeigt nur
        an. Geklickt wird dort nichts: `safe_click` blockiert jeden
        Kaufbutton, und `safe_goto` verhindert, dass die Pfadsuche
        versehentlich auf `/checkout/finish` landet.
        """
        for path in ("/checkout/confirm", "/checkout/shippingPayment", "/checkout/register"):
            if not await safe_goto(page, urljoin(base_url, path), timeout=28.0):
                continue
            if await wait_for_text(
                page,
                ("zahlungsart", "zahlungsmethode", "versandart", "anmelden"),
                timeout=8.0,
            ):
                return True
        return await super().go_to_checkout(page, base_url, config)

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Shopware verlangt Gast-Registrierung mit personal*/billingAddress*-Feldern."""
        if await try_selectors(page, self.GUEST_CHECKOUT, timeout=1.2):
            await wait_for_selector_any(
                page,
                ("input[name='personalMail']", "input[name='email']", "#personalMail"),
                timeout=6.0,
            )

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
        return filled
