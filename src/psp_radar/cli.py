"""Kommandozeile.

Anders als beim Vorgänger ist der Standardmodus der **Trichter**: teurere
Stufen laufen nur, wenn das Ergebnis sonst unklar bliebe. Wer die volle
Tiefe erzwingen will, sagt es mit `--voll`.

Diese Umkehrung des Standards ist eine bewusste Entscheidung. Beim
Vorgänger war "immer alles" richtig, weil erst bewiesen werden musste, dass
die Erkennung überhaupt funktioniert. Jetzt ist bekannt, dass sie es tut —
und Listen abzuarbeiten ist der Regelfall.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from . import report as reporting
from .config import ScanConfig
from .core import ScanResult, load_registry
from .core.registry import SignatureError
from .scanner import scan

app = typer.Typer(
    name="psp-radar",
    help="Ermittelt Zahlungsdienstleister hinter Shop-URLs.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


@app.command("scan")
def scan_command(
    url: Annotated[str, typer.Argument(help="Shop-URL")],
    voll: Annotated[
        bool, typer.Option("--voll", help="Immer bis in den Checkout, auch wenn früher schon klar")
    ] = False,
    schnell: Annotated[
        bool, typer.Option("--schnell", help="Ohne Checkout-Simulation")
    ] = False,
    statisch: Annotated[
        bool, typer.Option("--statisch", help="Nur ohne Browser — wenige Sekunden")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    evidence: Annotated[bool, typer.Option("--evidence", help="Volle Belegtabelle")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
    headed: Annotated[bool, typer.Option("--headed", help="Browser sichtbar, zur Fehlersuche")] = False,
    save_db: Annotated[Path | None, typer.Option("--save", help="In SQLite ablegen")] = None,
    timeout: Annotated[float, typer.Option("--timeout")] = 220.0,
) -> None:
    """Scannt einen einzelnen Shop."""
    config = ScanConfig(
        auto_depth=not voll,
        enable_checkout=not schnell and not statisch,
        enable_render=not statisch,
        headless=not headed,
        total_timeout=timeout,
    )

    if as_json:
        result = asyncio.run(scan(url, config))
        print(reporting.to_json(result))
    else:
        with console.status(f"[cyan]Scanne {url}…[/]"):
            result = asyncio.run(scan(url, config))
        reporting.print_result(result, console, verbose=verbose)
        if evidence:
            console.print()
            reporting.print_evidence_table(result, console)

    if save_db is not None:
        from .batch.store import save

        save(result, save_db)

    raise typer.Exit(0 if result.primary_psp else 2)


@app.command("batch")
def batch_command(
    input_file: Annotated[Path, typer.Argument(help="CSV oder TXT, eine URL pro Zeile")],
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("ergebnisse.csv"),
    concurrency: Annotated[int, typer.Option("-c", "--concurrency", help="Shops parallel")] = 6,
    voll: Annotated[bool, typer.Option("--voll", help="Trichter abschalten")] = False,
    db: Annotated[Path | None, typer.Option("--db", help="Cache und Ablage")] = None,
    cache_days: Annotated[int, typer.Option("--cache-days")] = 30,
) -> None:
    """Arbeitet eine Liste von Shops ab."""
    from .batch import run_batch
    from .batch.funnel import BatchProgress

    urls = _read_urls(input_file)
    if not urls:
        err.print("[red]Keine URLs gefunden.[/]")
        raise typer.Exit(1)

    config = ScanConfig(auto_depth=not voll, concurrency=concurrency)
    console.print(f"[bold]{len(urls)}[/] Shops · {concurrency} parallel · Trichter {'aus' if voll else 'an'}")

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as bar:
        task = bar.add_task("Scanne…", total=len(urls))

        def on_progress(progress: BatchProgress) -> None:
            bar.update(task, completed=progress.done, description=progress.current[:44])

        results = asyncio.run(
            run_batch(urls, config, db_path=db, cache_days=cache_days, on_progress=on_progress)
        )

    if output.suffix.lower() == ".json":
        output.write_text(reporting.results_to_json(results), encoding="utf-8")
    else:
        with output.open("w", encoding="utf-8", newline="") as handle:
            reporting.write_csv(results, handle)

    _summary(results, output)


def _summary(results: list[ScanResult], output: Path) -> None:
    found = [r for r in results if r.primary_psp]
    seconds = sum(r.duration_s for r in results)

    table = Table(title="Zusammenfassung", header_style="bold")
    table.add_column("Kennzahl")
    table.add_column("Wert", justify="right")
    table.add_row("Shops", str(len(results)))
    table.add_row("PSP erkannt", f"{len(found)}  ({len(found) / max(len(results), 1):.0%})")
    table.add_row("Ø Dauer je Shop", f"{seconds / max(len(results), 1):.1f} s")
    table.add_row("Gesamtdauer", f"{seconds / 60:.1f} min Rechenzeit")
    console.print(table)

    # Nach Trichterstufe: zeigt, wie viel der Trichter tatsächlich gespart hat
    tiers: dict[str, int] = {}
    for r in results:
        tiers[r.tier] = tiers.get(r.tier, 0) + 1
    if tiers:
        stufen = Table(title="Nach Trichterstufe", header_style="bold")
        stufen.add_column("Stufe", style="cyan")
        stufen.add_column("Shops", justify="right")
        for name, count in sorted(tiers.items(), key=lambda kv: -kv[1]):
            stufen.add_row(name, str(count))
        console.print(stufen)

    counts: dict[str, int] = {}
    for r in found:
        assert r.primary_psp is not None
        counts[r.primary_psp.name] = counts.get(r.primary_psp.name, 0) + 1
    if counts:
        verteilung = Table(title="Verteilung", header_style="bold")
        verteilung.add_column("PSP", style="cyan")
        verteilung.add_column("Shops", justify="right")
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            verteilung.add_row(name, str(count))
        console.print(verteilung)

    console.print(f"\n[green]✓[/] Gespeichert: [bold]{output}[/]")


@app.command("serve")
def serve_command(
    port: Annotated[int, typer.Option("--port", "-p")] = 8765,
    host: Annotated[str, typer.Option("--host", help="0.0.0.0 für Codespaces und Container")] = "127.0.0.1",
    db: Annotated[Path | None, typer.Option("--db")] = None,
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
) -> None:
    """Startet die Weboberfläche."""
    from .api import serve

    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    console.print(f"\n  [bold]psp-radar[/] auf [bold cyan]http://{shown}:{port}[/]")
    console.print("  [dim]Beenden mit Strg+C[/]\n")

    if not no_browser and host == "127.0.0.1":
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    serve(host=host, port=port, db_path=db)


@app.command("doctor")
def doctor_command() -> None:
    """Prüft die Umgebung: Python, Signaturen, Chromium, Netzwerk.

    Zuerst ausführen, wenn Ergebnisse leer bleiben. Ein fehlender Browser
    sieht wie ein Erkennungsproblem aus, ist aber ein Einrichtungsfehler —
    und führt die Fehlersuche sonst in die völlig falsche Richtung.
    """
    from .doctor import run

    raise typer.Exit(run(console))


@app.command("signatures")
def signatures_command(
    check: Annotated[bool, typer.Option("--check")] = False,
) -> None:
    """Zeigt oder prüft die Signatur-Datenbank."""
    try:
        registry = load_registry()
    except SignatureError as exc:
        err.print(f"[red]Signatur-Datenbank fehlerhaft:[/]\n{exc}")
        raise typer.Exit(1) from exc

    stats = registry.stats()
    if check:
        console.print(f"[green]✓[/] {stats['total']} Signaturen, {stats['signals']} Signale — valide")
        raise typer.Exit(0)

    table = Table(title=f"Signaturen ({registry.version})", header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Rolle")
    table.add_column("Signale", justify="right")
    for signature in sorted(registry.signatures, key=lambda s: (str(s.role), s.name)):
        table.add_row(signature.id, signature.name, str(signature.role), str(len(signature.signals)))
    console.print(table)


@app.command("eval")
def eval_command(
    golden: Annotated[Path, typer.Option("--golden")] = Path("tests/golden_set.yaml"),
    live: Annotated[bool, typer.Option("--live", help="Echte Shops statt Fixtures")] = False,
    aufzeichnen: Annotated[
        bool,
        typer.Option(
            "--aufzeichnen",
            help="Rohaufzeichnungen als Fixtures einfrieren (nur mit --live)",
        ),
    ] = False,
) -> None:
    """Misst Precision, Recall und Laufzeit gegen das Golden-Set."""
    from .eval import run_evaluation

    if not golden.exists():
        err.print(f"[red]Golden-Set nicht gefunden:[/] {golden}")
        raise typer.Exit(1)

    if aufzeichnen and not live:
        err.print(
            "[red]--aufzeichnen braucht --live.[/] Im Fixture-Modus gibt es "
            "nichts aufzuzeichnen."
        )
        raise typer.Exit(1)

    metrics = asyncio.run(run_evaluation(golden, live=live, record=aufzeichnen))
    metrics.print(console)
    raise typer.Exit(0 if metrics.passes_target() else 1)


def _read_urls(path: Path) -> list[str]:
    """Liest URLs aus CSV oder Textdatei, tolerant gegenüber beiden Formaten."""
    if not path.exists():
        err.print(f"[red]Datei nicht gefunden:[/] {path}")
        raise typer.Exit(1)

    text = path.read_text(encoding="utf-8")
    urls: list[str] = []

    if path.suffix.lower() == ".csv":
        rows = list(csv.reader(text.splitlines()))
        if not rows:
            return []
        header = [c.strip().lower() for c in rows[0]]
        column = next(
            (i for i, name in enumerate(header) if name in ("url", "domain", "shop", "website", "link")),
            0,
        )
        body = rows[1:] if any(h in ("url", "domain", "shop", "website", "link") for h in header) else rows
        urls = [row[column].strip() for row in body if row and len(row) > column and row[column].strip()]
    else:
        urls = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    seen: set[str] = set()
    eindeutig: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            eindeutig.append(u)
    return eindeutig


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        err.print("\n[yellow]Abgebrochen.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
