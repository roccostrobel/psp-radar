"""Stufe 1 — passive Signale ohne Browser.

Schnell, günstig und überraschend ergiebig. Der grösste Hebel steckt im
Content-Security-Policy-Header: Ein Shop muss dort jede Domain whitelisten,
mit der sein Checkout spricht — auch die, die erst viel später geladen wird.
Wer die CSP liest, sieht den Zahlungsdienstleister oft, bevor überhaupt ein
Produkt im Warenkorb liegt.
"""

from __future__ import annotations

import asyncio

import httpx

from ..config import ScanConfig
from ..core.models import ScanWarning, Stage
from ..core.observation import Observation, extract_srcs, strip_tags
from .normalize import NormalizeResult

#: Pfade, die ein Shop-System verraten oder Zahlungsinfos preisgeben.
#: Alle öffentlich und ohne Authentifizierung erreichbar.
WELLKNOWN_PATHS: tuple[tuple[str, str], ...] = (
    ("/products.json", "shopify"),
    ("/wp-json/wc/store/v1/products", "woocommerce"),
    ("/store-api/context", "shopware"),
    ("/.well-known/apple-developer-merchantid-domain-association", "apple_pay"),
    ("/.well-known/apple-developer-merchantid-domain-association.txt", "apple_pay"),
)

#: Zusätzlich besuchte Seiten. Impressum und AGB nennen den
#: Zahlungsdienstleister im DACH-Raum erstaunlich oft im Klartext —
#: die Informationspflicht spielt uns hier in die Hände.
EXTRA_PAGES: tuple[str, ...] = (
    "/impressum",
    "/datenschutz",
    "/agb",
    "/zahlungsarten",
    "/versand-und-zahlung",
    "/checkout",
    "/warenkorb",
    "/cart",
    "/privacy-policy",
)


def _headers_lower(response: httpx.Response) -> dict[str, str]:
    return {k.lower(): v for k, v in response.headers.items()}


def _observation_from_response(
    response: httpx.Response, stage: Stage = Stage.STATIC
) -> Observation:
    html = response.text if "text" in response.headers.get("content-type", "") else ""
    scripts, iframes = extract_srcs(html)

    obs = Observation(
        stage=stage,
        source_url=str(response.url),
        html=html,
        headers=_headers_lower(response),
        cookies={c.name: c.value for c in response.cookies.jar},
        script_srcs=scripts,
        iframe_srcs=iframes,
        dom_text=strip_tags(html),
    )
    obs.merge_csp_from_headers()
    return obs


async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except httpx.HTTPError:
        return None


async def _probe_wellknown(
    client: httpx.AsyncClient, base_url: str
) -> tuple[list[str], list[Observation]]:
    """Prüft bekannte Pfade und bestätigt sie inhaltlich.

    Ein HTTP 200 allein genügt nicht: Viele Shops liefern für unbekannte
    Pfade eine 200er-Fehlerseite aus. Deshalb wird der Inhalt gegengeprüft
    statt nur der Statuscode.
    """
    from urllib.parse import urljoin

    hits: list[str] = []
    observations: list[Observation] = []

    async def check(path: str, marker: str) -> None:
        response = await _fetch(client, urljoin(base_url, path))
        if response is None or response.status_code != 200:
            return

        body = response.text[:4000]
        confirmed = False
        match marker:
            case "shopify":
                confirmed = '"products"' in body and "application/json" in response.headers.get(
                    "content-type", ""
                )
            case "woocommerce":
                confirmed = body.lstrip().startswith(("[", "{"))
            case "shopware":
                confirmed = '"salesChannel"' in body or '"token"' in body
            case "apple_pay":
                # Die Domain-Association-Datei ist eine unformatierte Textdatei
                confirmed = "html" not in response.headers.get("content-type", "").lower()
            case _:
                confirmed = True

        if confirmed:
            hits.append(path)
            observations.append(_observation_from_response(response))

    await asyncio.gather(*(check(p, m) for p, m in WELLKNOWN_PATHS))
    return hits, observations


async def collect_static(
    normalized: NormalizeResult, config: ScanConfig
) -> tuple[list[Observation], list[ScanWarning]]:
    """Sammelt alle Signale, die ohne JavaScript-Ausführung zu holen sind."""
    from urllib.parse import urljoin

    observations: list[Observation] = []
    warnings: list[ScanWarning] = []

    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": config.accept_language,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=config.static_timeout,
        headers=headers,
        http2=True,
    ) as client:
        # Startseite
        home = await _fetch(client, normalized.final_url)
        if home is not None:
            observations.append(_observation_from_response(home))
        else:
            warnings.append(
                ScanWarning(
                    code="static_home_failed",
                    message="Startseite konnte statisch nicht geladen werden",
                    stage=Stage.STATIC,
                )
            )

        # Well-known-Pfade
        hits, wk_obs = await _probe_wellknown(client, normalized.final_url)
        observations.extend(wk_obs)
        if hits and observations:
            observations[0].wellknown_hits = hits

        # Zusatzseiten, gedrosselt und robots-konform
        for path in EXTRA_PAGES:
            target = urljoin(normalized.final_url, path)
            if not normalized.may_fetch(target, config.user_agent, config.respect_robots):
                continue

            response = await _fetch(client, target)
            if response is not None and response.status_code == 200 and len(response.text) > 500:
                observations.append(_observation_from_response(response))

            await asyncio.sleep(config.delay_between_requests * 0.3)

    return observations, warnings
