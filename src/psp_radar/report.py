"""Darstellung der Ergebnisse.

Grundsatz: Jede Zahl, die das Tool ausgibt, muss auf Nachfrage einen Beleg
liefern können. Deshalb ist die Belegkette Teil der Standardausgabe und
keine versteckte Debug-Option.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TextIO

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from .core.models import Detection, Role, ScanResult

_COLOR = {
    "sicher": "bold green",
    "wahrscheinlich": "yellow",
    "moeglich": "orange3",
    "schwach": "dim red",
}

_LABEL = {
    "sicher": "sicher",
    "wahrscheinlich": "wahrscheinlich",
    "moeglich": "möglich",
    "schwach": "schwach",
}


def _fmt(detection: Detection) -> str:
    label = str(detection.confidence_label)
    style = _COLOR.get(label, "white")
    text = f"[{style}]{detection.confidence}%  {_LABEL.get(label, label)}[/]"
    if detection.underlying:
        text += f"  [dim](Unterbau: {detection.underlying})[/]"
    return text


#: Wie die Herkunft eines Acquirer-Funds dargestellt wird.
#: Die Reihenfolge der Ausgabe folgt der Belastbarkeit, nicht der Zahl.
_QUELLE = {
    "beobachtet": ("bold green", "im Checkout beobachtet"),
    "angegeben": ("green", "vom Händler angegeben"),
    "vermutet": ("yellow", "nur indirekte Spuren"),
    "keine": ("red", "nicht ermittelt"),
}


def fortschritt(result: ScanResult) -> str:
    """Wie weit die Simulation gekommen ist — in drei Stufen, nicht in zwei.

    Beides fällt auseinander: Bei snocks.com wurde die Checkout-Seite
    erreicht und Shopify Payments zu 98 % erkannt, die Zahlungsauswahl
    selbst aber nicht. Ein blosses "Checkout erreicht ✓" neben der Warnung
    "Zahlungsauswahl nicht erreicht" widerspricht sich für den Leser.
    """
    if result.payment_selection_reached:
        return "[green]Zahlungsauswahl erreicht ✓[/]"
    if result.checkout_reached:
        return "[yellow]Checkout-Seite erreicht, Zahlungsauswahl nicht[/]"
    return "[yellow]ohne Checkout[/]"


def print_result(result: ScanResult, console: Console | None = None, *, verbose: bool = False) -> None:
    """Menschenlesbare Ausgabe im Terminal.

    Die Reihenfolge ist bewusst gewählt: erst das, was das Tool belegen
    kann, dann die offene Frage. Umgekehrt gelesen entsteht der Eindruck,
    ein Scan ohne Acquirer sei ein Fehlschlag — dabei sind Shop-System und
    Zahlungsarten für sich schon eine brauchbare Auskunft, und der Acquirer
    ist ohne Checkout nur bei etwa einem Viertel der DACH-Shops überhaupt
    bestimmbar (docs/BEFUNDE.md).
    """
    console = console or Console()
    tree = Tree(f"[bold]{result.final_domain or result.url}[/]")

    # --- Belegt: Shop-System und Zahlungsarten ---
    belegt = tree.add("[bold]Belegt[/]")

    if result.platform:
        belegt.add(f"Shop-System    [cyan]{result.platform.name}[/]  {_fmt(result.platform)}")
    else:
        belegt.add("Shop-System    [dim]unbekannt[/]")

    if result.wallets or result.payment_methods:
        names = [d.name for d in (*result.wallets, *result.payment_methods)]
        belegt.add(f"Zahlungsarten  [green]{', '.join(names)}[/]")
    else:
        belegt.add("Zahlungsarten  [dim]keine erkannt[/]")

    if result.fraud_tools:
        belegt.add(f"Fraud/Risk     [dim]{', '.join(d.name for d in result.fraud_tools)}[/]")

    # --- Die offene Frage: wer wickelt ab? ---
    stil, bezeichnung = _QUELLE[result.acquirer_source]
    kopf = f"[bold]Zahlungsabwickler[/]  [{stil}]{bezeichnung}[/]"
    zweig = tree.add(kopf)

    if result.psps:
        for detection in result.psps:
            role_hint = " [dim](Orchestrator)[/]" if detection.role == Role.ORCHESTRATOR else ""
            node = zweig.add(f"[bold cyan]{detection.name}[/]{role_hint}  {_fmt(detection)}")
            for item in detection.evidence[: 6 if verbose else 3]:
                node.add(
                    f"[dim]{item.matched_value}[/]  "
                    f"[dim italic]({item.signal_type}, Stufe {item.stage}, Gewicht {item.weight})[/]"
                )
    zweig.add(f"[dim italic]{result.acquirer_note}[/]")

    # --- Herkunft des Ergebnisses ---
    tree.add(
        f"[dim]Herkunft[/]       Stufe {result.tier} · {fortschritt(result)} · {result.duration_s:.1f}s"
    )

    console.print(tree)

    if result.warnings:
        console.print()
        for warning in result.warnings:
            console.print(f"[yellow]![/] [dim]{warning.code}:[/] {warning.message}")


def print_evidence_table(result: ScanResult, console: Console | None = None) -> None:
    """Vollständige Belegtabelle — für die manuelle Gegenprüfung."""
    console = console or Console()
    table = Table(title="Belege", show_lines=False, header_style="bold")
    table.add_column("Anbieter", style="cyan")
    table.add_column("Signal")
    table.add_column("Gefunden", overflow="fold", max_width=52)
    table.add_column("Stufe")
    table.add_column("Gew.", justify="right")

    everything = [
        *result.psps,
        *result.wallets,
        *result.payment_methods,
        *result.fraud_tools,
    ]
    if result.platform:
        everything.insert(0, result.platform)

    for detection in everything:
        for item in detection.evidence:
            table.add_row(
                detection.name,
                str(item.signal_type),
                item.matched_value,
                str(item.stage),
                str(item.weight),
            )

    console.print(table)


def to_json(result: ScanResult, *, indent: int = 2) -> str:
    return result.model_dump_json(indent=indent, exclude_none=False)


CSV_COLUMNS = (
    "url",
    "final_domain",
    "platform",
    "platform_confidence",
    "psp",
    "psp_confidence",
    #: Woher die Aussage stammt: beobachtet / angegeben / vermutet / keine.
    #: Gehört neben die Zahl, nicht in eine Fussnote — zwei Zeilen mit 92 %
    #: sind nicht gleichwertig, wenn eine aus dem Checkout und eine aus
    #: einem Verbindungshinweis stammt.
    "psp_quelle",
    "psp_underlying",
    "psp_alle",
    "zahlungsarten",
    "wallets",
    "fraud_tools",
    "checkout_erreicht",
    "zahlungsauswahl_erreicht",
    "gesamt_confidence",
    "dauer_s",
    "warnungen",
)


def result_to_row(result: ScanResult) -> dict[str, str]:
    """Eine Zeile für den CSV-Export."""
    primary = result.primary_psp
    return {
        "url": result.url,
        "final_domain": result.final_domain or "",
        "platform": result.platform.name if result.platform else "",
        "platform_confidence": str(result.platform.confidence) if result.platform else "",
        "psp": primary.name if primary else "",
        "psp_confidence": str(primary.confidence) if primary else "",
        "psp_quelle": result.acquirer_source,
        "psp_underlying": (primary.underlying or "") if primary else "",
        "psp_alle": "; ".join(f"{d.name}({d.confidence})" for d in result.psps),
        "zahlungsarten": "; ".join(d.name for d in result.payment_methods),
        "wallets": "; ".join(d.name for d in result.wallets),
        "fraud_tools": "; ".join(d.name for d in result.fraud_tools),
        "checkout_erreicht": "ja" if result.checkout_reached else "nein",
        "zahlungsauswahl_erreicht": "ja" if result.payment_selection_reached else "nein",
        "gesamt_confidence": str(result.overall_confidence),
        "dauer_s": f"{result.duration_s:.1f}",
        "warnungen": "; ".join(w.code for w in result.warnings),
    }


def write_csv(results: list[ScanResult], stream: TextIO) -> None:
    writer = csv.DictWriter(stream, fieldnames=list(CSV_COLUMNS))
    writer.writeheader()
    for result in results:
        writer.writerow(result_to_row(result))


def results_to_csv(results: list[ScanResult]) -> str:
    buffer = StringIO()
    write_csv(results, buffer)
    return buffer.getvalue()


def results_to_json(results: list[ScanResult]) -> str:
    return json.dumps([json.loads(r.model_dump_json()) for r in results], indent=2, ensure_ascii=False)
