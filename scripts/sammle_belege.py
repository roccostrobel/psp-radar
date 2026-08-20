"""Sammelt Zahlungsseiten mehrerer Shops, damit ein Mensch sie lesen kann.

Zweck: Golden-Set aufbauen, ohne die Erkennung des Tools als Wahrheit zu
verwenden. Das Skript **beurteilt nichts** — es holt die Seiten, findet die
Stellen, an denen ein Dienstleister genannt sein könnte, und gibt die Sätze
im Volltext aus. Die Zuordnung macht danach ein Mensch.

Das ist der entscheidende Unterschied zu `verified_via: tool_observed`:
Dort war die Schlussfolgerung des Tools der Beleg. Hier ist der Beleg ein
Satz, den der Händler selbst geschrieben hat.

    python scripts/sammle_belege.py shops.txt
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from psp_radar.collect.static import (
    PAYMENT_PAGES,
    finde_zahlungsseiten,
    looks_like_payment_page,
)
from psp_radar.config import DEFAULT_UA
from psp_radar.core.observation import strip_tags

#: Nach diesen Namen wird gesucht. Absichtlich breit — auch Anbieter ohne
#: eigene Signatur sollen auffallen, sonst findet man nie die Lücken.
ANBIETER = re.compile(
    r"\b("
    r"Unzer|Payolution|heidelpay|Computop|PAYONE|Novalnet|secupay|micropayment|"
    r"VR[ -]?Payment|CardProcess|Datatrans|Saferpay|wallee|mPAY24|Payrexx|"
    r"Stripe|Adyen|Mollie|Braintree|Checkout\.com|Worldline|Ingenico|Ogone|"
    r"Nexi|Concardis|Nets|SumUp|Mangopay|Klarna|Ratepay|Billie|easyCredit|"
    r"Riverty|AfterPay|Shopify Payments|Amazon Pay|PayPal|Sofort|TWINT|"
    r"Crefopay|Novalnet|Micropayment|Paydirekt|giropay|Wirecard|BS PAYONE|"
    r"Concardis|EVO Payments|Elavon|Nuvei|Buckaroo|Multisafepay|Klik|"
    r"Bank Frick|Ratenkauf"
    r")\b",
    re.IGNORECASE,
)

#: Sätze, die auf eine Abwicklungsaussage hindeuten — dort steht der
#: eigentliche Dienstleister, nicht nur eine angebotene Zahlungsart.
ABWICKLUNG = re.compile(
    r"(abgewickelt|Abwicklung|Dienstleister|Zahlungsdienstleister|abgetreten|"
    r"Abtretung|Kaufpreisanspruch|in Zusammenarbeit mit|erfolgt über|"
    r"technischer Dienstleister|Zahlungsabwicklung)",
    re.IGNORECASE,
)


async def hole_direkt(
    client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore
) -> tuple[str, str] | None:
    async with semaphore:
        return await hole(client, url)


async def hole(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    try:
        antwort = await client.get(url)
    except httpx.HTTPError:
        return None
    if antwort.status_code != 200 or len(antwort.text) < 500:
        return None
    return str(antwort.url), strip_tags(antwort.text)


def saetze_mit_anbieter(text: str) -> list[str]:
    """Zerlegt in Sätze und behält die mit Anbieternamen."""
    treffer: list[str] = []
    for satz in re.split(r"(?<=[.!?])\s+", text):
        if len(satz) > 400:
            satz = satz[:400] + " …"
        if ANBIETER.search(satz):
            treffer.append(satz.strip())
    return treffer


async def pruefe_shop(shop: str) -> None:
    basis = shop if "://" in shop else f"https://{shop}"
    domain = urlparse(basis).hostname or shop

    print("\n" + "═" * 78)
    print(f"  {domain}")
    print("═" * 78)

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=20.0, headers=headers, http2=True
    ) as client:
        semaphore = asyncio.Semaphore(4)

        async def eine(pfad: str) -> tuple[str, str] | None:
            async with semaphore:
                return await hole(client, urljoin(basis, pfad))

        # Erst die Startseite, um die verlinkten Zahlungsseiten zu finden.
        # Geratene Pfade allein finden zu wenig: Lokalpraefixe und
        # Dateiendungen weichen von Shop zu Shop ab.
        start = await hole(client, basis)
        entdeckt: list[str] = []
        if start is not None:
            try:
                roh = (await client.get(basis)).text
                entdeckt = finde_zahlungsseiten(roh, basis)
            except httpx.HTTPError:
                entdeckt = []

        if entdeckt:
            print(f"  Im Footer verlinkt: {len(entdeckt)} Seite(n)")
            for u in entdeckt:
                print(f"    · {u}")

        aufgaben = [eine(p) for p in PAYMENT_PAGES]
        aufgaben += [hole_direkt(client, u, semaphore) for u in entdeckt]
        ergebnisse = await asyncio.gather(*aufgaben)

    gefunden = False
    gesehen: set[str] = set()

    for eintrag in ergebnisse:
        if eintrag is None:
            continue
        url, text = eintrag
        if url in gesehen or not looks_like_payment_page(url, text):
            continue
        gesehen.add(url)

        saetze = saetze_mit_anbieter(text)
        if not saetze:
            continue

        gefunden = True
        print(f"\n  ▸ {url}")
        # Abwicklungssätze zuerst — die sind die eigentliche Aussage
        wichtig = [s for s in saetze if ABWICKLUNG.search(s)]
        rest = [s for s in saetze if s not in wichtig]

        for satz in wichtig[:4]:
            print(f"\n    ★ {satz}")
        for satz in rest[:6]:
            print(f"\n      {satz}")

    if not gefunden:
        print("\n  Keine Zahlungsseite mit Anbieternamen gefunden.")
        print("  → Muss im Browser über den Checkout geprüft werden.")


async def main(shops: list[str]) -> None:
    for shop in shops:
        await pruefe_shop(shop)
        await asyncio.sleep(1.0)  # höflich gegenüber den Shops


if __name__ == "__main__":
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        liste = [
            z.strip()
            for z in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
            if z.strip() and not z.startswith("#")
        ]
    else:
        liste = sys.argv[1:]
    asyncio.run(main(liste))
