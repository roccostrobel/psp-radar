"""Stufe 3 — Checkout-Simulation.

Die entscheidende Stufe. Hier zeigt sich, mit wem ein Shop tatsächlich
abrechnet, weil der PSP an dieser Stelle zwangsläufig geladen wird.

Ablauf: Produkt → Warenkorb → Checkout → Adresse → Zahlungsauswahl.
**Dort ist Ende.** Es wird keine Bestellung ausgelöst, keine
Zahlungsinformation eingegeben und kein Konto angelegt. Die Prüfung dagegen
sitzt in `adapters.base.safe_click` und greift vor jedem einzelnen Klick.

Scheitert die Simulation — und sie scheitert bei ungewöhnlich gebauten
Shops durchaus —, liefert das Tool trotzdem das Ergebnis aus Stufe 1 und 2,
markiert mit `checkout_reached: false`. Ein eingeschränktes Ergebnis mit
ehrlichem Hinweis ist mehr wert als ein abgebrochener Scan.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError

from ..config import ScanConfig
from ..core.models import ScanWarning, Stage
from ..core.observation import Observation
from .adapters import pick_adapter
from .adapters.shopify import ShopifyAdapter
from .browser import Recorder, snapshot
from .normalize import NormalizeResult


@dataclass
class CheckoutOutcome:
    """Ergebnis der Simulation."""

    reached_payment: bool
    reached_checkout_page: bool
    observations: list[Observation] = field(default_factory=list)
    warnings: list[ScanWarning] = field(default_factory=list)
    #: Wie weit es gekommen ist — hilfreich für die Fehlersuche
    steps: list[str] = field(default_factory=list)


async def simulate_checkout(
    context: BrowserContext,
    recorder: Recorder,
    normalized: NormalizeResult,
    config: ScanConfig,
    *,
    platform_id: str | None = None,
    product_url: str | None = None,
) -> CheckoutOutcome:
    """Führt die Simulation bis zur Zahlungsauswahl."""
    adapter = pick_adapter(platform_id)
    outcome = CheckoutOutcome(reached_payment=False, reached_checkout_page=False)
    outcome.steps.append(f"Adapter: {adapter.name}")

    page = await context.new_page()
    try:
        # --- Produkt bestimmen ---
        if platform_id == "shopify" and product_url is None:
            product_url = await ShopifyAdapter.first_product_url(page, normalized.final_url)

        if product_url is None:
            outcome.warnings.append(
                ScanWarning(
                    code="checkout_no_product",
                    message="Kein Produkt gefunden — Checkout-Simulation nicht möglich",
                    stage=Stage.CHECKOUT,
                )
            )
            return outcome

        mark = len(recorder.urls)

        try:
            await page.goto(product_url, wait_until="domcontentloaded", timeout=config.page_timeout * 1000)
            await asyncio.sleep(1.5)
        except PlaywrightError:
            outcome.warnings.append(
                ScanWarning(
                    code="checkout_product_unreachable",
                    message=f"Produktseite nicht erreichbar: {product_url}",
                    stage=Stage.CHECKOUT,
                )
            )
            return outcome

        outcome.steps.append(f"Produkt geöffnet: {product_url}")

        # --- In den Warenkorb ---
        if not await adapter.add_to_cart(page, config):
            outcome.warnings.append(
                ScanWarning(
                    code="checkout_add_to_cart_failed",
                    message="Produkt liess sich nicht in den Warenkorb legen",
                    stage=Stage.CHECKOUT,
                )
            )
            outcome.observations.append(await snapshot(page, recorder, Stage.CHECKOUT, since=mark))
            return outcome

        outcome.steps.append("In den Warenkorb gelegt")
        await asyncio.sleep(config.delay_between_requests)

        # --- Warenkorb und Checkout ---
        await adapter.go_to_cart(page, normalized.final_url, config)
        outcome.steps.append("Warenkorb geöffnet")

        if not await adapter.go_to_checkout(page, normalized.final_url, config):
            outcome.warnings.append(
                ScanWarning(
                    code="checkout_page_unreachable",
                    message="Checkout-Seite nicht erreichbar",
                    stage=Stage.CHECKOUT,
                )
            )
            outcome.observations.append(await snapshot(page, recorder, Stage.CHECKOUT, since=mark))
            return outcome

        outcome.reached_checkout_page = True
        outcome.steps.append(f"Checkout erreicht: {page.url}")
        # Zwischenstand sichern — hier laden viele PSPs bereits
        outcome.observations.append(await snapshot(page, recorder, Stage.CHECKOUT, since=mark))

        # --- Adresse und Zahlungsauswahl ---
        if await adapter.at_payment_selection(page):
            outcome.reached_payment = True
        else:
            await adapter.fill_guest_details(page, config)
            outcome.steps.append("Gastdaten eingetragen")
            await adapter.advance(page, config, steps=3)
            outcome.reached_payment = await adapter.at_payment_selection(page)

        await asyncio.sleep(3.0)  # PSP-Iframes brauchen einen Moment
        outcome.observations.append(await snapshot(page, recorder, Stage.CHECKOUT, since=mark))

        if outcome.reached_payment:
            outcome.steps.append("Zahlungsauswahl erreicht — Simulation hier beendet")
        else:
            outcome.warnings.append(
                ScanWarning(
                    code="checkout_payment_not_reached",
                    message=(
                        "Zahlungsauswahl nicht erreicht. Ergebnis stützt sich auf "
                        "Checkout-Vorstufe und Stufe 1/2."
                    ),
                    stage=Stage.CHECKOUT,
                )
            )

    except Exception as exc:
        outcome.warnings.append(
            ScanWarning(
                code="checkout_error",
                message=f"Unerwarteter Fehler in der Simulation: {exc.__class__.__name__}: {exc}",
                stage=Stage.CHECKOUT,
            )
        )
    finally:
        # Warenkorb-Session verwerfen — es bleibt nichts zurück
        with contextlib.suppress(PlaywrightError):
            await page.close()

    return outcome
