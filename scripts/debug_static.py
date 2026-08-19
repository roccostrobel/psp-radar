"""Zeigt, was Stufe 1 tatsächlich einsammelt.

Diagnosewerkzeug. Bei bergfreunde.de blieb der Zahlungsdienstleister leer,
obwohl er auf der Seite "Lieferung und Zahlung" im Klartext steht. Dieses
Skript beantwortet die Frage, an welcher Stelle er verloren geht: schon beim
Abruf, bei der Einstufung als Zahlungsseite, beim Textauszug oder beim
Abgleich.

    python scripts/debug_static.py https://www.bergfreunde.de
"""

from __future__ import annotations

import asyncio
import re
import sys

from psp_radar.collect import collect_static, normalize
from psp_radar.config import ScanConfig
from psp_radar.core import load_registry, match_all

GESUCHT = re.compile(
    r"unzer|payolution|heidelpay|computop|payone|novalnet|adyen|stripe|mollie|"
    r"saferpay|datatrans|nexi|concardis|worldline|ratepay|klarna",
    re.IGNORECASE,
)


async def main(url: str) -> None:
    config = ScanConfig()
    normalized = await normalize(url, config)
    print(f"Ziel: {normalized.final_url}  erreichbar={normalized.reachable}\n")

    observations, warnings = await collect_static(normalized, config)
    print(f"{len(observations)} Seite(n) eingesammelt\n")

    print(f"{'ZAHLUNGSSEITE':<14} {'TEXTLÄNGE':>10}  {'HTML':>9}  URL")
    print("-" * 100)
    for obs in observations:
        marke = "JA" if obs.is_payment_page else "nein"
        print(f"{marke:<14} {len(obs.dom_text):>10}  {len(obs.html):>9}  {obs.source_url[:58]}")

    print("\n=== Anbieternamen im Textauszug ===")
    irgendwo = False
    for obs in observations:
        treffer = sorted({t.lower() for t in GESUCHT.findall(obs.dom_text)})
        if treffer:
            irgendwo = True
            marke = "Zahlungsseite" if obs.is_payment_page else "andere Seite"
            print(f"  [{marke}] {obs.source_url[:60]}")
            print(f"      {', '.join(treffer)}")
    if not irgendwo:
        print("  (keiner) — der Name steht nicht im ausgewerteten Text")

    print("\n=== Anbieternamen im ROH-HTML (vor dem Textauszug) ===")
    for obs in observations:
        treffer = sorted({t.lower() for t in GESUCHT.findall(obs.html)})
        nur_im_html = treffer and not GESUCHT.search(obs.dom_text)
        if nur_im_html:
            print(f"  !! {obs.source_url[:60]}")
            print(f"      {', '.join(treffer)} — im HTML vorhanden, im Textauszug NICHT")
            print("      → der Textauszug schneidet zu früh ab")

    print("\n=== Evidenz aus dem Abgleich ===")
    evidence = match_all(load_registry(), observations)
    if not evidence:
        print("  (keine)")
    for sig_id, items in sorted(evidence.items()):
        beste = max(items, key=lambda e: e.weight)
        print(f"  {sig_id:<20} {beste.weight:>3}  {beste.signal_type}  {beste.matched_value[:60]!r}")

    if warnings:
        print("\n=== Warnungen ===")
        for w in warnings:
            print(f"  {w.code}: {w.message[:110]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "https://www.bergfreunde.de"))
