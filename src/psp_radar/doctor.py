"""Selbsttest der Umgebung.

Entstanden aus einem konkreten Ärgernis: Im Codespace fehlte Chromium, weil
`playwright install --with-deps` Root braucht und im Setup scheiterte. Die
Oberfläche zeigte daraufhin "Kein Zahlungsdienstleister ermittelt" und einen
Playwright-Stacktrace — es sah aus wie ein Erkennungsproblem, war aber ein
Einrichtungsfehler.

Diese Verwechslung ist teuer, weil sie in die falsche Richtung führt: Man
sucht nach fehlenden Signaturen, während der Browser gar nicht startet.
`psp-radar doctor` beantwortet die Frage vorher und in einfachen Worten.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table


@dataclass
class Pruefung:
    name: str
    ok: bool
    detail: str
    #: Was zu tun ist, wenn es nicht in Ordnung ist
    abhilfe: str = ""
    #: Kritisch heisst: Ohne das läuft das Tool nicht vollständig
    kritisch: bool = True


def pruefe_python() -> Pruefung:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 12)
    return Pruefung(
        "Python", ok, version, "Python 3.12 oder neuer nötig" if not ok else ""
    )


def pruefe_signaturen() -> Pruefung:
    try:
        from .core import load_registry

        stats = load_registry().stats()
        return Pruefung(
            "Signatur-Datenbank",
            True,
            f"{stats['total']} Signaturen, {stats['signals']} Signale",
        )
    except Exception as exc:
        return Pruefung(
            "Signatur-Datenbank",
            False,
            f"{exc.__class__.__name__}: {exc}",
            "psp-radar signatures --check zeigt die genaue Stelle",
        )


def pruefe_playwright_paket() -> Pruefung:
    try:
        import playwright

        version = getattr(playwright, "__version__", "unbekannt")
        return Pruefung("Playwright-Paket", True, f"Version {version}")
    except ImportError:
        return Pruefung(
            "Playwright-Paket",
            False,
            "nicht installiert",
            'pip install -e ".[dev]"',
        )


async def _chromium_startet() -> tuple[bool, str]:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            version = browser.version
            await browser.close()
            return True, f"startet, Version {version}"
    except Exception as exc:
        return False, str(exc).split("\n")[0][:150]


def pruefe_chromium() -> Pruefung:
    """Die Prüfung, um die es eigentlich geht.

    Nicht nur ob die Datei existiert, sondern ob der Browser wirklich
    startet. Ein vorhandenes Binary ohne passende Systembibliotheken
    scheitert genauso, nur mit unverständlicherer Meldung.
    """
    ok, detail = asyncio.run(_chromium_startet())
    pfad = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "(Standardpfad)")
    return Pruefung(
        "Chromium",
        ok,
        detail if ok else f"{detail}  [Suchpfad: {pfad}]",
        "playwright install chromium — im Codespace prüfen, ob "
        "PLAYWRIGHT_BROWSERS_PATH auf /ms-playwright zeigt",
    )


def pruefe_netzwerk() -> Pruefung:
    """Erreicht das Tool das Internet? Ohne das ist alles andere müssig."""
    try:
        import httpx

        antwort = httpx.get("https://example.com", timeout=8.0)
        return Pruefung(
            "Internetzugang", antwort.status_code == 200, f"HTTP {antwort.status_code}"
        )
    except Exception as exc:
        return Pruefung(
            "Internetzugang",
            False,
            f"{exc.__class__.__name__}",
            "Ohne Netzwerkzugang kann kein Shop geprüft werden",
        )


def pruefe_zugangscode() -> Pruefung:
    code = os.environ.get("PSP_RADAR_ACCESS_CODE", "").strip()
    if code:
        return Pruefung("Zugangscode", True, "gesetzt", kritisch=False)
    return Pruefung(
        "Zugangscode",
        True,
        "nicht gesetzt — in Ordnung lokal und im Codespace, Pflicht bei "
        "öffentlicher Erreichbarkeit",
        kritisch=False,
    )


def pruefe_git() -> Pruefung:
    vorhanden = shutil.which("git") is not None
    return Pruefung(
        "git", vorhanden, "vorhanden" if vorhanden else "fehlt", kritisch=False
    )


def run(console: Console | None = None) -> int:
    """Führt alle Prüfungen aus. Rückgabe ist der Exit-Code."""
    console = console or Console()

    pruefungen = [
        pruefe_python(),
        pruefe_signaturen(),
        pruefe_playwright_paket(),
        pruefe_chromium(),
        pruefe_netzwerk(),
        pruefe_zugangscode(),
        pruefe_git(),
    ]

    tabelle = Table(title="psp-radar Selbsttest", header_style="bold")
    tabelle.add_column("", justify="center", width=3)
    tabelle.add_column("Prüfung")
    tabelle.add_column("Ergebnis", overflow="fold")

    for p in pruefungen:
        if p.ok:
            zeichen = "[green]✓[/]"
        elif p.kritisch:
            zeichen = "[red]✗[/]"
        else:
            zeichen = "[yellow]![/]"
        tabelle.add_row(zeichen, p.name, p.detail)

    console.print(tabelle)

    fehler = [p for p in pruefungen if not p.ok and p.kritisch]
    if not fehler:
        console.print("\n[green]Alles bereit.[/] Die Erkennung kann vollständig arbeiten.\n")
        return 0

    console.print("\n[bold red]Nicht einsatzbereit.[/] Zu beheben:\n")
    for p in fehler:
        console.print(f"  [red]✗[/] [bold]{p.name}[/]: {p.detail}")
        if p.abhilfe:
            console.print(f"      → {p.abhilfe}")

    if any(p.name == "Chromium" for p in fehler):
        console.print(
            "\n[yellow]Hinweis:[/] Ohne Chromium laufen nur die statischen Stufen. "
            "Ergebnisse bleiben dann oft leer, weil der Zahlungsdienstleister erst "
            "im Checkout sichtbar wird — das sieht wie ein Erkennungsproblem aus, "
            "ist aber keins."
        )
    console.print()
    return 1
