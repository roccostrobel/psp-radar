"""Schreibt die Importpfade von psp-detector auf die neue Struktur um.

Einmalig genutzt beim Umzug. Bewusst als Skript und nicht per Hand: 25
Dateien mit teils mehrdeutigen relativen Importen sind eine ideale Quelle
für stille Fehler, die erst zur Laufzeit auffallen.

Die neue Aufteilung:

    core/      reine Logik, kein Netzwerk, kein Browser
    collect/   Beschaffung (httpx, Playwright, Adapter)
    batch/     Trichter, Warteschlange, Cache
    eval/      Golden-Set, Fixtures, Messung
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "psp_radar"

#: Pro Verzeichnis: (Suchmuster, Ersetzung). Reihenfolge zählt — die
#: spezifischeren Regeln müssen vor den allgemeinen stehen.
RULES: dict[str, list[tuple[str, str]]] = {
    "core": [
        (r"from \.\.models import", "from .models import"),
        (r"from \.\.registry import", "from .registry import"),
        (r"from \.\.scoring import", "from .scoring import"),
        (r"from \.\.observation import", "from .observation import"),
        (r"from \.\.matching import", "from .matching import"),
    ],
    "collect/adapters": [
        (r"from \.\.config import", "from ...config import"),
    ],
    "collect": [
        # Kern liegt jetzt eine Ebene tiefer in core/
        (r"from \.\.models import", "from ..core.models import"),
        (r"from \.\.observation import", "from ..core.observation import"),
        (r"from \.\.registry import", "from ..core.registry import"),
        (r"from \.\.matching import", "from ..core.matching import"),
        (r"from \.\.scoring import", "from ..core.scoring import"),
        # Geschwister innerhalb von collect/
        (r"from \.\.browser import", "from .browser import"),
        (r"from \.\.adapters import", "from .adapters import"),
        (r"from \.\.adapters\.", "from .adapters."),
        (r"from \.s0_normalize import", "from .normalize import"),
        (r"from \.s1_static import", "from .static import"),
        (r"from \.s2_render import", "from .render import"),
        (r"from \.s3_checkout import", "from .checkout import"),
        # browser.py lag vorher im Paketwurzelverzeichnis
        (r"from \.config import", "from ..config import"),
        (r"from \.models import", "from ..core.models import"),
        (r"from \.observation import", "from ..core.observation import"),
    ],
    "batch": [
        (r"from \.models import", "from ..core.models import"),
    ],
    "eval": [
        (r"from \.matching import", "from ..core.matching import"),
        (r"from \.models import", "from ..core.models import"),
        (r"from \.observation import", "from ..core.observation import"),
        (r"from \.registry import", "from ..core.registry import"),
        (r"from \.scoring import", "from ..core.scoring import"),
        (r"from \.pipeline\.s4_fuse import", "from ..core.fuse import"),
        (r"from \.pipeline import", "from ..collect import"),
        (r"from \.scanner import", "from ..scanner import"),
        (r"from \.config import", "from ..config import"),
    ],
}

#: Dateien direkt unter psp_radar/
ROOT_RULES: list[tuple[str, str]] = [
    (r"from \.models import", "from .core.models import"),
    (r"from \.registry import", "from .core.registry import"),
    (r"from \.scoring import", "from .core.scoring import"),
    (r"from \.matching import", "from .core.matching import"),
    (r"from \.observation import", "from .core.observation import"),
    (r"from \.browser import", "from .collect.browser import"),
    (r"from \.pipeline\.s4_fuse import", "from .core.fuse import"),
    (r"from \.pipeline import", "from .collect import"),
    (r"from \.store import", "from .batch.store import"),
    (r"from \.evaluation import", "from .eval.golden import"),
]


def apply(path: Path, rules: list[tuple[str, str]]) -> int:
    text = original = path.read_text(encoding="utf-8")
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)
    if text == original:
        return 0
    path.write_text(text, encoding="utf-8")
    return sum(
        1
        for a, b in zip(original.splitlines(), text.splitlines(), strict=False)
        if a != b
    )


def main() -> None:
    if not ROOT.exists():
        sys.exit(f"Nicht gefunden: {ROOT}")

    total = 0
    # Tiefste Pfade zuerst, damit collect/adapters vor collect greift
    for folder in sorted(RULES, key=lambda p: -p.count("/")):
        directory = ROOT / folder
        if not directory.exists():
            continue
        for file in sorted(directory.glob("*.py")):
            changed = apply(file, RULES[folder])
            if changed:
                print(f"  {folder}/{file.name}: {changed} Zeile(n)")
                total += changed

    for file in sorted(ROOT.glob("*.py")):
        changed = apply(file, ROOT_RULES)
        if changed:
            print(f"  {file.name}: {changed} Zeile(n)")
            total += changed

    print(f"\n{total} Importzeile(n) umgeschrieben.")


if __name__ == "__main__":
    main()
