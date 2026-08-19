"""Bewacht die Schichtentrennung.

Der Kern muss frei von Netzwerk und Browser bleiben. Das ist keine
Stilfrage: Genau diese Trennung macht es möglich, die gesamte
Erkennungslogik offline und deterministisch gegen eingefrorene Fixtures zu
prüfen. Ohne sie bräuchte jeder Test einen echten Shop — und damit wäre die
Vorgabe "schneller, aber ohne Qualitätsverlust" nicht mehr überprüfbar.

Solche Regeln erodieren nicht mit einem Knall, sondern durch einen
naheliegenden Import, den niemand hinterfragt. Deshalb steht hier ein Test
und nicht nur ein Satz in der Dokumentation.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "src" / "psp_radar" / "core"
PACKAGE = CORE.parent

#: Was der Kern nicht anfassen darf
VERBOTEN_IM_KERN = {
    "playwright",
    "httpx",
    "fastapi",
    "uvicorn",
    "sqlite3",
    "socket",
    "urllib.request",
}

VERBOTENE_GESCHWISTER = {"collect", "batch", "api", "web", "eval", "scanner", "cli", "report"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            # Relative Importe: level sagt, wie viele Ebenen hoch
            if node.level and node.level >= 2:
                names.add(f"__hoch{node.level}__:{node.module}")
    return names


def test_kern_hat_keine_io_abhaengigkeiten() -> None:
    verstoesse: list[str] = []
    for file in sorted(CORE.glob("*.py")):
        for imported in _imports(file):
            wurzel = imported.split(".")[0]
            if wurzel in VERBOTEN_IM_KERN or imported in VERBOTEN_IM_KERN:
                verstoesse.append(f"core/{file.name} importiert {imported}")

    assert not verstoesse, (
        "Der Kern muss frei von Netzwerk und Browser bleiben:\n  - " + "\n  - ".join(verstoesse)
    )


def test_kern_importiert_keine_geschwisterschichten() -> None:
    """core darf nicht aus collect, batch, api oder scanner importieren."""
    verstoesse: list[str] = []
    for file in sorted(CORE.glob("*.py")):
        text = file.read_text(encoding="utf-8")
        for schicht in VERBOTENE_GESCHWISTER:
            for muster in (f"from ..{schicht}", f"from psp_radar.{schicht}"):
                if muster in text:
                    verstoesse.append(f"core/{file.name}: {muster}")

    assert not verstoesse, (
        "Der Kern steht unter allen anderen Schichten und darf nicht nach oben "
        "greifen:\n  - " + "\n  - ".join(verstoesse)
    )


def test_kern_ist_ohne_optionale_pakete_importierbar() -> None:
    """Der Kern muss auch ohne installiertes Playwright oder FastAPI laden.

    Praktischer Nutzen: Die Evaluation gegen Fixtures läuft damit in der CI
    ohne Browser-Installation — in Sekunden statt in Minuten.
    """
    import importlib

    modul = importlib.import_module("psp_radar.core")
    assert hasattr(modul, "fuse")
    assert hasattr(modul, "match_all")
    assert hasattr(modul, "load_registry")


def test_observation_ist_serialisierbar() -> None:
    """Die Voraussetzung für offline reproduzierbare Tests."""
    import json

    from psp_radar.core import Observation, Stage

    original = Observation(
        stage=Stage.CHECKOUT,
        source_url="https://shop.de/checkout",
        network_urls=["https://api.unzer.com/v1/payments"],
        headers={"content-security-policy": "frame-src https://*.unzer.com"},
    )
    wieder = Observation.model_validate(json.loads(original.model_dump_json()))

    assert wieder.network_urls == original.network_urls
    assert wieder.headers == original.headers
    assert wieder.stage == original.stage


def test_signaturen_liegen_im_kern() -> None:
    """Die Signatur-Datenbank gehört zum Kern, nicht zur Beschaffung."""
    signaturen = list((CORE / "signatures").glob("*.yaml"))
    assert len(signaturen) >= 3, "Signaturdateien fehlen im Kern"
    assert not list((PACKAGE / "collect").glob("*.yaml"))
