"""Messung der Erkennungsgüte gegen das Golden-Set.

Ohne diese Datei wäre das Tool ein Versprechen. Mit ihr ist es eine
überprüfbare Aussage.

Zwei Betriebsarten:

- **Fixture-Modus (Standard)** — rechnet gegen eingefrorene Observations.
  Deterministisch, offline, in Sekunden durch. Läuft in der CI.
- **Live-Modus** — scannt die echten Shops. Aufwendig, aber der einzige Weg,
  neue Fixtures zu erzeugen und Veränderungen im echten Web zu bemerken.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from ..core.matching import match_all
from ..core.models import Evidence, ScanResult, Stage
from ..core.observation import Observation
from ..core.registry import load_registry

#: Zielwerte für v1.0
TARGET_RECALL = 0.90
TARGET_PRECISION = 0.95

FIXTURE_DIR = Path("tests/fixtures")


@dataclass
class GoldenEntry:
    """Ein Shop mit manuell verifiziertem Ergebnis."""

    url: str
    expected_psp: str
    expected_platform: str | None = None
    #: Wie wurde verifiziert? Pflichtangabe — eine Behauptung ohne Beleg
    #: ist im Golden-Set schlimmer als gar kein Eintrag.
    verified_via: str = ""
    verified_at: str = ""
    note: str = ""
    fixture: str | None = None


@dataclass
class Outcome:
    entry: GoldenEntry
    predicted_psp: str | None
    predicted_platform: str | None
    confidence: int

    @property
    def psp_correct(self) -> bool:
        return self.predicted_psp == self.entry.expected_psp

    @property
    def platform_correct(self) -> bool:
        if self.entry.expected_platform is None:
            return True
        return self.predicted_platform == self.entry.expected_platform


@dataclass
class Metrics:
    """Precision, Recall und die Einzelfälle dahinter."""

    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def predicted(self) -> list[Outcome]:
        """Fälle, in denen das Tool überhaupt eine Aussage gemacht hat."""
        return [o for o in self.outcomes if o.predicted_psp is not None]

    @property
    def correct(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.psp_correct]

    @property
    def recall(self) -> float:
        """Anteil der Shops, deren PSP korrekt gefunden wurde."""
        return len(self.correct) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        """Anteil der Aussagen, die stimmen. Schweigen zählt nicht als Fehler."""
        made = self.predicted
        return len([o for o in made if o.psp_correct]) / len(made) if made else 0.0

    @property
    def platform_accuracy(self) -> float:
        relevant = [o for o in self.outcomes if o.entry.expected_platform]
        return (
            len([o for o in relevant if o.platform_correct]) / len(relevant) if relevant else 0.0
        )

    def passes_target(self) -> bool:
        return self.recall >= TARGET_RECALL and self.precision >= TARGET_PRECISION

    def by_psp(self) -> dict[str, tuple[int, int]]:
        """Je erwartetem PSP: (korrekt, gesamt)."""
        buckets: dict[str, tuple[int, int]] = {}
        for outcome in self.outcomes:
            correct, total = buckets.get(outcome.entry.expected_psp, (0, 0))
            buckets[outcome.entry.expected_psp] = (
                correct + int(outcome.psp_correct),
                total + 1,
            )
        return dict(sorted(buckets.items(), key=lambda kv: -kv[1][1]))

    def print(self, console: Console | None = None) -> None:
        console = console or Console()

        summary = Table(title="Erkennungsgüte", header_style="bold")
        summary.add_column("Kennzahl")
        summary.add_column("Wert", justify="right")
        summary.add_column("Ziel", justify="right")
        summary.add_column("", justify="center")

        for label, value, target in (
            ("Recall (PSP gefunden)", self.recall, TARGET_RECALL),
            ("Precision (Aussage korrekt)", self.precision, TARGET_PRECISION),
        ):
            ok = value >= target
            summary.add_row(
                label,
                f"[{'green' if ok else 'red'}]{value:.1%}[/]",
                f"{target:.0%}",
                "[green]✓[/]" if ok else "[red]✗[/]",
            )
        summary.add_row("Shop-System korrekt", f"{self.platform_accuracy:.1%}", "—", "")
        summary.add_row("Shops im Set", str(self.total), "—", "")
        console.print(summary)

        per_psp = Table(title="Nach Anbieter", header_style="bold")
        per_psp.add_column("Erwartet", style="cyan")
        per_psp.add_column("Korrekt", justify="right")
        per_psp.add_column("Gesamt", justify="right")
        for name, (correct, total) in self.by_psp().items():
            style = "green" if correct == total else "red" if correct == 0 else "yellow"
            per_psp.add_row(name, f"[{style}]{correct}[/]", str(total))
        console.print(per_psp)

        failures = [o for o in self.outcomes if not o.psp_correct]
        if failures:
            console.print("\n[bold red]Abweichungen:[/]")
            for outcome in failures:
                got = outcome.predicted_psp or "nichts erkannt"
                console.print(
                    f"  [dim]{outcome.entry.url}[/] — erwartet [cyan]{outcome.entry.expected_psp}[/], "
                    f"erhalten [red]{got}[/] ({outcome.confidence}%)"
                )


def load_golden(path: Path) -> list[GoldenEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [GoldenEntry(**entry) for entry in raw.get("shops", [])]


def load_fixture(name: str, directory: Path = FIXTURE_DIR) -> list[Observation]:
    """Lädt eingefrorene Observations."""
    path = directory / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Observation.model_validate(item) for item in data["observations"]]


def save_fixture(name: str, observations: list[Observation], directory: Path = FIXTURE_DIR) -> Path:
    """Friert Observations für deterministische Tests ein."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(
        json.dumps(
            {"observations": [json.loads(o.model_dump_json()) for o in observations]},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def evaluate_observations(observations: list[Observation]) -> ScanResult:
    """Lässt Erkennung und Fusion über fertige Observations laufen.

    Genau der Teil, der offline testbar sein muss: alles nach der
    Datenbeschaffung.
    """
    from ..core.fuse import fuse
    from ..scanner import best_platform_id

    registry = load_registry()
    preliminary: dict[str, list[Evidence]] = match_all(registry, observations)
    platform_id = best_platform_id(registry, preliminary)
    evidence = match_all(registry, observations, detected_platform=platform_id)

    return fuse(
        registry,
        evidence,
        url=observations[0].source_url if observations else "",
        final_url=observations[0].source_url if observations else None,
        final_domain=None,
        checkout_reached=any(o.stage == Stage.CHECKOUT for o in observations),
        stages_run=sorted({o.stage for o in observations}, key=str),
        warnings=[],
        duration_s=0.0,
    )


async def run_evaluation(golden_path: Path, *, live: bool = False) -> Metrics:
    """Rechnet das Golden-Set durch."""
    entries = load_golden(golden_path)
    metrics = Metrics()

    for entry in entries:
        if live:
            from ..scanner import scan

            result = await scan(entry.url)
        else:
            fixture_name = entry.fixture or entry.url.replace("https://", "").replace("/", "_")
            try:
                observations = load_fixture(fixture_name)
            except FileNotFoundError:
                continue  # noch keine Fixture aufgezeichnet
            result = evaluate_observations(observations)

        primary = result.primary_psp
        metrics.outcomes.append(
            Outcome(
                entry=entry,
                predicted_psp=primary.id if primary else None,
                predicted_platform=result.platform.id if result.platform else None,
                confidence=primary.confidence if primary else 0,
            )
        )

    return metrics
