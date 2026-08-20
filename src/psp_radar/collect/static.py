"""Stufe 1 — passive Signale ohne Browser.

Schnell, günstig und überraschend ergiebig. Der grösste Hebel steckt im
Content-Security-Policy-Header: Ein Shop muss dort jede Domain whitelisten,
mit der sein Checkout spricht — auch die, die erst viel später geladen wird.
Wer die CSP liest, sieht den Zahlungsdienstleister oft, bevor überhaupt ein
Produkt im Warenkorb liegt.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

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

#: Zahlungsinformationsseiten. Die ergiebigste billige Quelle im DACH-Raum:
#: Händler benennen ihren Dienstleister dort im Klartext, oft weil sie es
#: müssen. Bei bergfreunde.de steht auf `/lieferung-und-zahlung/` wörtlich
#: "Der Zahlungsprozess wird über unseren Dienstleister Payolution/Unzer
#: abgewickelt" — die Antwort auf die Kernfrage, für zwei Sekunden Aufwand.
#:
#: Die Liste ist bewusst lang. Jeder Eintrag kostet einen parallelen
#: HTTP-Abruf; ein fehlender Eintrag kostet ein ganzes Ergebnis. Genau
#: dieser Pfad fehlte und war der Grund, warum bergfreunde.de leer blieb.
PAYMENT_PAGES: tuple[str, ...] = (
    "/lieferung-und-zahlung",
    "/lieferung-zahlung",
    "/versand-und-zahlung",
    "/versand-zahlung",
    "/zahlung-und-versand",
    "/zahlungsarten",
    "/zahlungsmethoden",
    "/zahlungsmoeglichkeiten",
    "/zahlung",
    "/bezahlung",
    "/bezahlmoeglichkeiten",
    "/versandkosten",
    "/lieferung",
    "/hilfe/zahlung",
    "/service/zahlungsarten",
    "/service/lieferung-und-zahlung",
    "/info/zahlungsarten",
    "/payment",
    "/payment-methods",
    "/shipping-and-payment",
)

#: Rechtsseiten. Schwächer als die Zahlungsseiten, aber Impressum und AGB
#: nennen den Abwickler oder die abtretungsempfangende Bank gelegentlich.
LEGAL_PAGES: tuple[str, ...] = (
    "/impressum",
    "/agb",
    "/datenschutz",
    "/privacy-policy",
    "/terms",
)

#: Seiten des Kaufprozesses. Manche Shops laden dort bereits PSP-Skripte,
#: auch ohne gefüllten Warenkorb.
FLOW_PAGES: tuple[str, ...] = (
    "/checkout",
    "/warenkorb",
    "/cart",
    "/kasse",
    "/checkout/cart",
)

EXTRA_PAGES: tuple[str, ...] = PAYMENT_PAGES + LEGAL_PAGES + FLOW_PAGES


def _headers_lower(response: httpx.Response) -> dict[str, str]:
    return {k.lower(): v for k, v in response.headers.items()}


#: Überschriften und Textmarken, die eine Seite als Zahlungsinformationsseite
#: ausweisen. Zusätzlich zum Pfad geprüft, weil viele Shops solche Inhalte
#: unter eigenwilligen URLs führen — und weil eine 200er-Fehlerseite unter
#: `/zahlungsarten` sonst als Zahlungsseite gälte.
PAYMENT_PAGE_MARKERS: tuple[str, ...] = (
    "zahlungsart",
    "zahlungsmethode",
    "zahlungsmittel",
    "zahlungsmöglichkeit",
    "lieferung und zahlung",
    "versand und zahlung",
    "zahlung und versand",
    "bezahlmöglichkeit",
    "wie möchtest du bezahlen",
    "payment method",
)


#: Linktexte im Footer, die auf eine Zahlungsinformationsseite führen.
#: Der Footer ist dafür die verlässlichste Stelle — dort verlinken Shops
#: ihre Pflichtinformationen.
LINK_MARKERS: tuple[str, ...] = (
    "zahlungsart",
    "zahlungsmethode",
    "zahlungsmittel",
    "zahlungsmöglichkeit",
    "zahlung",
    "bezahlen",
    "bezahlung",
    "lieferung und zahlung",
    "versand und zahlung",
    "versand & zahlung",
    "zahlung und versand",
    "liefer- und zahlungsbedingungen",
    "payment",
    "shipping",
)


def finde_zahlungsseiten(html: str, basis_url: str, grenze: int = 8) -> list[str]:
    """Sucht Links zu Zahlungsinformationsseiten im HTML der Startseite.

    Der wichtigere Weg als eine feste Pfadliste. Geratene Pfade scheitern an
    Lokalpräfixen und Dateiendungen: thomann.de führt seine Seite unter
    `/de/zahlungsarten.html`, was weder `/zahlungsarten` noch
    `/zahlungsarten/` trifft. Bei einer Probe von acht Shops fand die
    Pfadliste genau einen — nicht weil die anderen schweigen, sondern weil
    die Adressen anders lauten.

    Shops verlinken ihre Pflichtinformationen im Footer. Diese Links zu
    lesen statt Adressen zu erraten ist der Unterschied zwischen einem
    Sonderfall und einer Methode.
    """
    gefunden: list[str] = []
    gesehen: set[str] = set()

    # href und Linktext zusammen betrachten: Manche Shops haben sprechende
    # Adressen, andere sprechende Texte, und beides zusammen trifft mehr.
    for treffer in re.finditer(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.{0,200}?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        href, inner = treffer.group(1), treffer.group(2)
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        linktext = re.sub(r"<[^>]+>", " ", inner).strip().lower()
        haystack = f"{href.lower()} {linktext}"

        if not any(marker in haystack for marker in LINK_MARKERS):
            continue

        ziel = urljoin(basis_url, href)
        # Nur innerhalb derselben Domain bleiben
        if urlparse(ziel).hostname != urlparse(basis_url).hostname:
            continue
        if ziel in gesehen:
            continue

        gesehen.add(ziel)
        gefunden.append(ziel)
        if len(gefunden) >= grenze:
            break

    return gefunden


def looks_like_payment_page(url: str, text: str) -> bool:
    """Ob eine Seite tatsächlich über Zahlungsarten informiert.

    Zwei Bedingungen, absichtlich beide: Die Adresse muss danach aussehen
    **und** der Text muss es bestätigen. Ein Shop, der für unbekannte Pfade
    eine 200er-Startseite ausliefert, würde sonst fälschlich als
    Zahlungsseite gelten — und dort ein zufällig erwähnter Anbietername
    bekäme das hohe Gewicht, das nur echten Aussagen zusteht.
    """
    low_url = url.lower()
    pfad_passt = any(
        teil in low_url
        for teil in (
            "zahl",
            "payment",
            "lieferung",
            "liefer",
            "versand",
            "bezahl",
            "shipping",
            "checkout",
        )
    )
    low_text = text[:40000].lower()
    text_passt = sum(marker in low_text for marker in PAYMENT_PAGE_MARKERS) >= 1
    return pfad_passt and text_passt


def _observation_from_response(
    response: httpx.Response, stage: Stage = Stage.STATIC
) -> Observation:
    html = response.text if "text" in response.headers.get("content-type", "") else ""
    scripts, iframes = extract_srcs(html)
    text = strip_tags(html)

    obs = Observation(
        stage=stage,
        source_url=str(response.url),
        html=html,
        headers=_headers_lower(response),
        cookies={c.name: c.value for c in response.cookies.jar},
        script_srcs=scripts,
        iframe_srcs=iframes,
        dom_text=text,
        is_payment_page=looks_like_payment_page(str(response.url), text),
    )
    obs.merge_csp_from_headers()
    return obs


async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except httpx.HTTPError:
        return None


async def hole_absolut(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
    normalized: NormalizeResult,
    config: ScanConfig,
) -> Observation | None:
    """Holt eine vollständige URL, robots-konform und gedrosselt."""
    if not normalized.may_fetch(url, config.user_agent, config.respect_robots):
        return None
    async with semaphore:
        antwort = await _fetch(client, url)
    if antwort is None or antwort.status_code != 200 or len(antwort.text) < 500:
        return None
    return _observation_from_response(antwort)


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
        # Zusatzseiten parallel, aber gedrosselt. Vorher sequenziell mit
        # Wartezeit dazwischen — bei jetzt 30 Pfaden wäre das über eine
        # Minute nur für HTTP-Abrufe. Die Drosselung auf wenige gleichzeitige
        # Verbindungen bleibt, weil ein Shop nicht mit 30 parallelen
        # Anfragen überzogen werden soll.
        semaphore = asyncio.Semaphore(config.static_concurrency)

        async def hole(path: str) -> Observation | None:
            target = urljoin(normalized.final_url, path)
            if not normalized.may_fetch(target, config.user_agent, config.respect_robots):
                return None
            async with semaphore:
                response = await _fetch(client, target)
            if response is None or response.status_code != 200 or len(response.text) < 500:
                return None
            return _observation_from_response(response)

        weitere = await asyncio.gather(*(hole(p) for p in EXTRA_PAGES))
        observations.extend(o for o in weitere if o is not None)

        # Zusätzlich die im Footer verlinkten Zahlungsseiten. Wichtiger als
        # die geratene Pfadliste: Bei einer Probe über acht Shops fand die
        # Liste nur einen, weil Lokalpräfixe (/de/) und Dateiendungen
        # (.html) nicht getroffen wurden.
        if home is not None:
            bereits = {o.source_url.rstrip("/") for o in observations}
            entdeckt = [
                u
                for u in finde_zahlungsseiten(home.text, normalized.final_url)
                if u.rstrip("/") not in bereits
            ]
            if entdeckt:
                aus_links = await asyncio.gather(*(hole_absolut(client, u, semaphore, normalized, config) for u in entdeckt))
                observations.extend(o for o in aus_links if o is not None)

    if not any(o.is_payment_page for o in observations):
        warnings.append(
            ScanWarning(
                code="no_payment_page",
                message=(
                    "Keine Zahlungsinformationsseite gefunden. Im DACH-Raum nennen "
                    "Shops den Dienstleister dort häufig im Klartext — fehlt die "
                    "Seite, entfällt eine der verlässlichsten Quellen."
                ),
                stage=Stage.STATIC,
            )
        )

    return observations, warnings
