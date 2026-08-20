"""Prüft, ob CSP-Header und Verbindungshinweise den Acquirer verraten.

Hintergrund: Die manuelle Verifikation an thomann.de zeigte, dass der
Acquirer bei vielen Shops erst nach der Zahlungsauswahl lädt — hinter der
Grenze, die aus Sicherheitsgründen nicht überschritten wird. Damit steht
die Kernfrage des Tools in Frage.

Es gibt aber Stellen, an denen ein Shop seinen PSP nennen **muss**, bevor
das Formular lädt:

1. **Content-Security-Policy.** Wer den PSP im Checkout einbettet, muss
   dessen Domain in `frame-src`, `connect-src`, `script-src` oder
   `form-action` whitelisten. Der Header liegt auf der Seite, nicht erst im
   Formular.
2. **Verbindungshinweise.** `<link rel="preconnect">` und `dns-prefetch`
   kündigen Hosts an, damit die Verbindung steht, bevor sie gebraucht wird —
   genau bei Zahlungsanbietern lohnt das, weshalb es dort häufig steht.
3. **Zahlungsseitentext.** Bereits umgesetzt.

Dieses Skript beantwortet, welche dieser Quellen tatsächlich etwas liefert,
und ob die Kombination reicht. Es verändert nichts am Tool — es misst.

    python scripts/pruefe_csp.py shops.txt
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from psp_radar.collect.static import finde_zahlungsseiten, looks_like_payment_page
from psp_radar.config import DEFAULT_UA
from psp_radar.core import load_registry
from psp_radar.core.models import Role, SignalType
from psp_radar.core.observation import strip_tags

#: Seiten, auf denen ein PSP-Hinweis am wahrscheinlichsten ist
KANDIDATEN = ("", "/checkout", "/warenkorb", "/cart", "/kasse", "/checkout/cart")

CSP_DIREKTIVEN = ("frame-src", "connect-src", "script-src", "form-action", "default-src", "child-src")


def gateway_hosts() -> dict[str, str]:
    """Alle Host-Muster der Gateways, abgebildet auf ihre Signatur-ID.

    Bewusst nur Gateways und Orchestratoren: Ein PayPal- oder Klarna-Host in
    der CSP sagt nichts über den Karten-Acquirer, und genau der ist die
    offene Frage.
    """
    registry = load_registry()
    zuordnung: dict[str, str] = {}
    for sig in registry.by_role(Role.GATEWAY, Role.ORCHESTRATOR):
        for signal in sig.signals:
            if signal.type in (SignalType.NETWORK_HOST, SignalType.CSP_DOMAIN):
                muster = signal.pattern.lower().lstrip("*").lstrip(".")
                zuordnung[muster] = sig.id
    return zuordnung


def csp_hosts(headers: dict[str, str]) -> set[str]:
    policy = " ".join(
        headers.get(name, "")
        for name in ("content-security-policy", "content-security-policy-report-only")
    )
    if not policy.strip():
        return set()

    gefunden: set[str] = set()
    for teil in policy.split(";"):
        stuecke = teil.strip().split()
        if not stuecke or stuecke[0].lower() not in CSP_DIREKTIVEN:
            continue
        for token in stuecke[1:]:
            token = token.strip().strip("'\"")
            if token.startswith("'") or (":" in token and "." not in token):
                continue
            host = token.removeprefix("https://").removeprefix("http://").split("/")[0]
            if "." in host:
                gefunden.add(host.lower())
    return gefunden


def hinweis_hosts(html: str) -> set[str]:
    """preconnect, dns-prefetch, preload und modulepreload."""
    gefunden: set[str] = set()
    for treffer in re.finditer(
        r'<link\s[^>]*rel=["\']?(preconnect|dns-prefetch|preload|modulepreload)["\']?[^>]*>',
        html,
        re.IGNORECASE,
    ):
        tag = treffer.group(0)
        href = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not href:
            continue
        ziel = href.group(1)
        if ziel.startswith("//"):
            ziel = "https:" + ziel
        host = urlparse(ziel).hostname
        if host:
            gefunden.add(host.lower())
    return gefunden


def treffer(hosts: set[str], zuordnung: dict[str, str]) -> dict[str, set[str]]:
    """Ordnet beobachtete Hosts den Gateway-IDs zu, streng auf Subdomains."""
    ergebnis: dict[str, set[str]] = defaultdict(set)
    for host in hosts:
        for muster, sig_id in zuordnung.items():
            if host == muster or host.endswith("." + muster):
                ergebnis[sig_id].add(host)
    return dict(ergebnis)


async def pruefe(shop: str, zuordnung: dict[str, str]) -> dict[str, object]:
    basis = shop if "://" in shop else f"https://{shop}"
    domain = urlparse(basis).hostname or shop

    kopf = {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": "de-DE,de;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    aus_csp: dict[str, set[str]] = {}
    aus_hinweisen: dict[str, set[str]] = {}
    aus_text: set[str] = set()
    csp_vorhanden = False

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=20.0, headers=kopf, http2=True
    ) as client:
        startseite = ""
        for pfad in KANDIDATEN:
            try:
                antwort = await client.get(urljoin(basis, pfad))
            except httpx.HTTPError:
                continue
            if antwort.status_code >= 400:
                continue

            kopfzeilen = {k.lower(): v for k, v in antwort.headers.items()}
            hosts = csp_hosts(kopfzeilen)
            if hosts:
                csp_vorhanden = True
                for sig_id, gesehen in treffer(hosts, zuordnung).items():
                    aus_csp.setdefault(sig_id, set()).update(gesehen)

            for sig_id, gesehen in treffer(hinweis_hosts(antwort.text), zuordnung).items():
                aus_hinweisen.setdefault(sig_id, set()).update(gesehen)

            if pfad == "":
                startseite = antwort.text
            await asyncio.sleep(0.4)

        # Zahlungsseiten für den Textabgleich
        if startseite:
            for url in finde_zahlungsseiten(startseite, basis)[:4]:
                try:
                    antwort = await client.get(url)
                except httpx.HTTPError:
                    continue
                if antwort.status_code != 200:
                    continue
                text = strip_tags(antwort.text)
                if not looks_like_payment_page(url, text):
                    continue
                for sig_id in _text_treffer(text):
                    aus_text.add(sig_id)
                await asyncio.sleep(0.4)

    return {
        "domain": domain,
        "csp_vorhanden": csp_vorhanden,
        "csp": aus_csp,
        "hinweise": aus_hinweisen,
        "text": aus_text,
    }


def _text_treffer(text: str) -> set[str]:
    """Gateway-IDs, die über payment_page_text im Text vorkommen."""
    registry = load_registry()
    gefunden: set[str] = set()
    for sig in registry.by_role(Role.GATEWAY, Role.ORCHESTRATOR):
        for signal in sig.signals:
            if signal.type != SignalType.PAYMENT_PAGE_TEXT:
                continue
            if re.search(signal.pattern, text, re.IGNORECASE):
                gefunden.add(sig.id)
    return gefunden


async def main(shops: list[str]) -> None:
    zuordnung = gateway_hosts()
    print(f"{len(zuordnung)} Gateway-Hostmuster in der Signaturdatenbank\n")

    ergebnisse = []
    for shop in shops:
        e = await pruefe(shop, zuordnung)
        ergebnisse.append(e)

        csp = ", ".join(sorted(e["csp"])) or "—"  # type: ignore[arg-type]
        hin = ", ".join(sorted(e["hinweise"])) or "—"  # type: ignore[arg-type]
        txt = ", ".join(sorted(e["text"])) or "—"  # type: ignore[arg-type]
        marke = "CSP vorhanden" if e["csp_vorhanden"] else "keine CSP"

        print(f"── {e['domain']}  ({marke})")
        print(f"     CSP        {csp}")
        print(f"     Hinweise   {hin}")
        print(f"     Text       {txt}")
        print()

    # Auswertung
    n = len(ergebnisse)
    mit_csp = sum(1 for e in ergebnisse if e["csp_vorhanden"])
    nur_csp = sum(1 for e in ergebnisse if e["csp"])
    nur_hin = sum(1 for e in ergebnisse if e["hinweise"])
    nur_txt = sum(1 for e in ergebnisse if e["text"])
    kombi = sum(
        1 for e in ergebnisse if e["csp"] or e["hinweise"] or e["text"]  # type: ignore[truthy-bool]
    )

    print("═" * 60)
    print(f"  Auswertung über {n} Shops")
    print("═" * 60)
    print(f"  CSP-Header überhaupt gesetzt      {mit_csp}/{n}")
    print(f"  Gateway aus CSP                   {nur_csp}/{n}")
    print(f"  Gateway aus Verbindungshinweisen  {nur_hin}/{n}")
    print(f"  Gateway aus Zahlungsseitentext    {nur_txt}/{n}")
    print(f"  Gateway aus KOMBINATION           {kombi}/{n}   ← entscheidend")
    print()


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
