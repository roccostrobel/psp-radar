"""Browser-Sitzung mit Netzwerk-Mitschnitt.

Der Kern der Genauigkeit: Jeder Request, den eine Seite absetzt, wird
protokolliert — auch die, die per JavaScript nachgeladen werden. Genau dort
tauchen die PSP-SDKs auf, die im statischen Quelltext nirgends stehen.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from ..config import ScanConfig
from ..core.models import Stage
from ..core.observation import Observation, strip_tags

#: Diese globalen JS-Objekte werden nach dem Laden abgefragt. Ihre blosse
#: Existenz verrät, welches SDK die Seite initialisiert hat.
PROBED_GLOBALS: tuple[str, ...] = (
    "Stripe",
    "AdyenCheckout",
    "Mollie",
    "braintree",
    "Klarna",
    "paypal",
    "Shopify",
    "Frames",
    "ApplePaySession",
    "prestashop",
    "requirejs",
    "wc_add_to_cart_params",
)

#: Ressourcentypen ohne Erkenntniswert. Blockieren spart deutlich Zeit,
#: ohne ein einziges relevantes Signal zu verlieren.
BLOCKED_RESOURCES = {"image", "media", "font"}


@dataclass
class Recorder:
    """Mitschnitt eines Browser-Contexts."""

    urls: list[str] = field(default_factory=list)
    response_headers: dict[str, dict[str, str]] = field(default_factory=dict)
    iframe_urls: set[str] = field(default_factory=set)
    script_urls: set[str] = field(default_factory=set)
    console_errors: list[str] = field(default_factory=list)

    def attach(self, context: BrowserContext) -> None:
        context.on("request", self._on_request)
        context.on("response", self._on_response)

    def _on_request(self, request: object) -> None:
        try:
            url = request.url  # type: ignore[attr-defined]
            rtype = request.resource_type  # type: ignore[attr-defined]
        except Exception:
            return

        if url.startswith(("data:", "blob:", "about:")):
            return

        self.urls.append(url)
        if rtype == "script":
            self.script_urls.add(url)
        elif rtype in ("document", "sub_frame"):
            self.iframe_urls.add(url)

    def _on_response(self, response: Response) -> None:
        try:
            if response.request.resource_type == "document":
                self.response_headers[response.url] = {
                    k.lower(): v for k, v in response.headers.items()
                }
        except Exception:
            return

    def headers_for(self, url: str) -> dict[str, str]:
        """Header der Dokument-Response, die am besten zu url passt."""
        if url in self.response_headers:
            return self.response_headers[url]
        for candidate, headers in self.response_headers.items():
            if candidate.rstrip("/") == url.rstrip("/"):
                return headers
        return next(iter(self.response_headers.values()), {})


@asynccontextmanager
async def browser_session(
    config: ScanConfig,
) -> AsyncIterator[tuple[BrowserContext, Recorder]]:
    """Startet Chromium mit realistischem Kontext und aktivem Mitschnitt."""
    playwright: Playwright = await async_playwright().start()
    browser: Browser | None = None
    try:
        browser = await playwright.chromium.launch(
            headless=config.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=config.user_agent,
            locale=config.locale,
            viewport={"width": config.viewport_width, "height": config.viewport_height},
            extra_http_headers={"Accept-Language": config.accept_language},
            ignore_https_errors=True,
        )
        context.set_default_timeout(config.page_timeout * 1000)

        if config.block_media:
            await context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in BLOCKED_RESOURCES
                    else route.continue_()
                ),
            )

        recorder = Recorder()
        recorder.attach(context)

        yield context, recorder
    finally:
        # Offene Route-Handler abräumen, bevor der Browser schliesst.
        # Sonst laufen noch fliegende Requests in einen geschlossenen
        # Target und Playwright wirft beim Beenden Fehler, die mit dem
        # eigentlichen Scan nichts zu tun haben.
        with contextlib.suppress(Exception):
            await context.unroute_all(behavior="ignoreErrors")
        if browser is not None:
            await browser.close()
        await playwright.stop()


async def probe_globals(page: Page) -> list[str]:
    """Fragt ab, welche der bekannten SDK-Globals vorhanden sind."""
    try:
        found: list[str] = await page.evaluate(
            """(names) => names.filter(n => typeof window[n] !== 'undefined')""",
            list(PROBED_GLOBALS),
        )
        return found
    except Exception:
        return []


async def snapshot(
    page: Page, recorder: Recorder, stage: Stage, *, since: int = 0
) -> Observation:
    """Friert den aktuellen Seitenzustand als Observation ein.

    `since` erlaubt es, nur die seit einem Zeitpunkt neu hinzugekommenen
    Requests zuzuordnen — so lässt sich sauber trennen, was beim Rendern
    und was erst im Checkout passiert ist.
    """
    try:
        html = await page.content()
    except Exception:
        html = ""

    try:
        cookies = {c["name"]: str(c.get("value", "")) for c in await page.context.cookies()}
    except Exception:
        cookies = {}

    iframe_srcs: list[str] = []
    try:
        for frame in page.frames:
            if frame.url and frame != page.main_frame:
                iframe_srcs.append(frame.url)
    except Exception:
        pass

    obs = Observation(
        stage=stage,
        source_url=page.url,
        html=html,
        headers=recorder.headers_for(page.url),
        cookies=cookies,
        network_urls=list(recorder.urls[since:]),
        script_srcs=sorted(recorder.script_urls),
        iframe_srcs=sorted(set(iframe_srcs) | recorder.iframe_urls),
        js_globals=await probe_globals(page),
        dom_text=strip_tags(html),
    )
    obs.merge_csp_from_headers()
    return obs
