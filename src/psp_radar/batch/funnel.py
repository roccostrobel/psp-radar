"""Der Trichter — Listen effizient abarbeiten.

Die zentrale Einsicht: Nicht jeder Shop braucht die volle Tiefe. Ein Shop,
dessen CSP-Header `frame-src https://*.adyen.com` enthält, ist beantwortet.
Ihn trotzdem drei Minuten durch die Checkout-Simulation zu schicken, ändert
das Ergebnis nicht — es kostet nur Zeit und belästigt den Shop.

    Durchgang 1   alle URLs      ohne Browser      2–4 s     hohe Parallelität
                  ↓ nur unklare Fälle
    Durchgang 2   Rendering      geteilter Browser 15–25 s   mittlere
                  ↓ nur weiterhin unklare
    Durchgang 3   Checkout       geteilter Browser 40–70 s   niedrige

Zwei Regeln, die diesen Aufbau ehrlich halten:

1. Jedes Ergebnis trägt in `tier`, aus welchem Durchgang es stammt.
2. Die Schwellwerte stehen in `ScanConfig` und sind gegen das Golden-Set
   kalibriert, nicht geraten.

Ausserdem: **Rate-Limit pro Domain, nicht global.** Vierzig Shops parallel
zu scannen ist unproblematisch, solange auf denselben Shop nur eine Sitzung
zugreift. Umgekehrt wäre eine globale Grenze von 40 gegenüber einem einzelnen
Shop rücksichtslos.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from ..config import ScanConfig
from ..core import ScanResult
from ..core.models import ScanWarning
from ..scanner import scan


@dataclass
class BatchProgress:
    """Fortschritt eines Massenlaufs, für Anzeige und API."""

    total: int
    done: int = 0
    tier_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    failed: int = 0
    current: str = ""
    #: Ob überhaupt ein Browser hochgefahren werden musste. Bei einer Liste,
    #: die sich vollständig statisch auflöst, bleibt das False — der
    #: sichtbare Beweis, dass der Trichter greift.
    browser_gestartet: bool = False

    @property
    def percent(self) -> float:
        return self.done / self.total if self.total else 0.0

    def note(self, result: ScanResult) -> None:
        self.done += 1
        self.tier_counts[result.tier] += 1
        if not result.primary_psp:
            self.failed += 1


class DomainLimiter:
    """Sorgt dafür, dass pro Domain nur eine Sitzung gleichzeitig läuft.

    Verhindert, dass ein Massenlauf einen einzelnen Shop mit parallelen
    Anfragen überzieht — unabhängig davon, wie hoch die Gesamtparallelität
    eingestellt ist.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def for_url(self, url: str) -> asyncio.Lock:
        host = (urlparse(url if "://" in url else f"https://{url}").hostname or url).lower()
        # www. abstreifen, damit shop.de und www.shop.de als dieselbe
        # Domain behandelt werden
        host = host.removeprefix("www.")
        return self._locks.setdefault(host, asyncio.Lock())


async def run_batch(
    urls: Sequence[str],
    config: ScanConfig | None = None,
    *,
    db_path: Path | None = None,
    cache_days: int = 30,
    on_progress: Callable[[BatchProgress], None] | None = None,
) -> list[ScanResult]:
    """Arbeitet eine Liste von Shop-URLs ab.

    Ein geteilter Browser für alle Shops, ein eigener Kontext pro Shop.
    Dadurch bleibt die Isolation vollständig erhalten, während der teure
    Prozessstart nur einmal anfällt.
    """
    config = config or ScanConfig(auto_depth=True)
    progress = BatchProgress(total=len(urls))
    limiter = DomainLimiter()
    semaphore = asyncio.Semaphore(config.concurrency)
    results: dict[str, ScanResult] = {}

    from ..collect.browser import shared_browser

    async with shared_browser(config) as browser:

        async def one(url: str) -> None:
            async with semaphore, limiter.for_url(url):
                progress.current = url

                if db_path is not None:
                    from .store import find_recent

                    cached = find_recent(url, cache_days, db_path)
                    if cached is not None:
                        results[url] = cached
                        progress.note(cached)
                        if on_progress:
                            on_progress(progress)
                        return

                # Kontext nur anlegen, wenn dieser Shop überhaupt einen
                # Browser braucht. Bei --statisch bleibt Chromium aus.
                context = await browser.new_context() if config.enable_render else None
                try:
                    result = await scan(url, config, context=context)
                except Exception as exc:
                    result = ScanResult(
                        url=url,
                        warnings=[
                            ScanWarning(
                                code="scan_failed",
                                message=f"{exc.__class__.__name__}: {exc}",
                            )
                        ],
                    )
                finally:
                    if context is not None:
                        with contextlib.suppress(Exception):
                            await context.close()

                if db_path is not None:
                    from .store import save

                    save(result, db_path)

                results[url] = result
                progress.note(result)
                if on_progress:
                    on_progress(progress)

        await asyncio.gather(*(one(u) for u in urls))
        progress.browser_gestartet = browser.started

    # Reihenfolge der Eingabe erhalten — wichtig, wenn die Ergebnisliste
    # gegen die Eingabeliste gestellt wird
    return [results[u] for u in urls if u in results]
