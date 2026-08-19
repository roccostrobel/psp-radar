"""Laden und Validieren der Signatur-Datenbank.

Die Erkennungsregeln stehen bewusst in YAML und nicht im Code. Einen neuen
Zahlungsdienstleister zu ergänzen heisst dadurch: einen YAML-Block
schreiben. Kein Refactoring, kein Deployment-Risiko, und die Regeln bleiben
für Menschen lesbar und prüfbar.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import REGEX_SIGNAL_TYPES, Role, Signal, SignalType, Signature

SIGNATURE_DIR = Path(__file__).parent / "signatures"


def regex_part(signal_type: SignalType, pattern: str) -> str:
    """Der tatsächlich als Regex auszuwertende Teil eines Patterns.

    Nur HEADER weicht ab: Dort steht vor dem Doppelpunkt der Headername,
    dahinter erst der Ausdruck.
    """
    if signal_type == SignalType.HEADER:
        return pattern.partition(":")[2].strip() or "."
    return pattern


class SignatureError(RuntimeError):
    """Die Signatur-Datenbank ist fehlerhaft."""


def _merge_by_id(signatures: list[Signature]) -> list[Signature]:
    """Führt Signaturen mit derselben ID zu einer zusammen.

    Erlaubt es, einen Anbieter über mehrere Dateien zu beschreiben: die
    technischen Fingerabdrücke in `gateways.yaml`, die Namenssignale für
    Zahlungsinformationsseiten in `names.yaml`. Beides in eine Datei zu
    zwingen würde entweder die Übersicht kosten oder dazu führen, dass die
    Namenssignale ganz wegfallen.

    Doppelte Signale — gleicher Typ, gleiches Muster — werden dabei
    entfernt, und zwar mit dem höheren Gewicht. Ein versehentliches
    Duplikat soll die Confidence nicht anheben.

    Widersprüchliche Rollen sind ein Fehler und werden gemeldet: Wäre ein
    Anbieter einmal `gateway` und einmal `method`, wäre unklar, in welche
    Spalte sein Ergebnis gehört.
    """
    zusammen: dict[str, Signature] = {}
    konflikte: list[str] = []

    for sig in signatures:
        vorhanden = zusammen.get(sig.id)
        if vorhanden is None:
            zusammen[sig.id] = sig
            continue

        if vorhanden.role != sig.role:
            konflikte.append(
                f"{sig.id}: Rolle einmal {vorhanden.role}, einmal {sig.role}"
            )
            continue

        # Signale nach (Typ, Muster) entdoppeln, höheres Gewicht gewinnt
        nach_schluessel: dict[tuple[str, str], Signal] = {
            (str(s.type), s.pattern): s for s in vorhanden.signals
        }
        for signal in sig.signals:
            schluessel = (str(signal.type), signal.pattern)
            bisher = nach_schluessel.get(schluessel)
            if bisher is None or signal.weight > bisher.weight:
                nach_schluessel[schluessel] = signal

        zusammen[sig.id] = vorhanden.model_copy(
            update={
                "signals": sorted(nach_schluessel.values(), key=lambda s: -s.weight),
                "aliases": sorted(set(vorhanden.aliases) | set(sig.aliases)),
                "regions": sorted(set(vorhanden.regions) | set(sig.regions)),
                "supersedes": sorted(set(vorhanden.supersedes) | set(sig.supersedes)),
                "underlying": vorhanden.underlying or sig.underlying,
                "requires_platform": vorhanden.requires_platform or sig.requires_platform,
                "homepage": vorhanden.homepage or sig.homepage,
            }
        )

    if konflikte:
        raise SignatureError(
            "Widersprüchliche Rollen in der Signatur-Datenbank:\n  - "
            + "\n  - ".join(konflikte)
        )

    return list(zusammen.values())


class Registry:
    """Alle bekannten Signaturen, indiziert für schnellen Zugriff."""

    def __init__(self, signatures: list[Signature], version: str) -> None:
        self.version = version
        self.signatures = _merge_by_id(signatures)
        self._by_id = {s.id: s for s in self.signatures}
        self._validate_references()

    def _validate_references(self) -> None:
        """Stellt sicher, dass underlying/requires_platform/supersedes existieren.

        Ein Tippfehler in einer Referenz würde sonst stillschweigend dazu
        führen, dass eine Regel nie greift — der unangenehmste Fehlertyp,
        weil er wie ein normales Negativergebnis aussieht.
        """
        errors: list[str] = []
        for sig in self.signatures:
            for field, value in (
                ("underlying", sig.underlying),
                ("requires_platform", sig.requires_platform),
            ):
                if value and value not in self._by_id:
                    errors.append(f"{sig.id}.{field} verweist auf unbekannte ID {value!r}")
            for target in sig.supersedes:
                if target not in self._by_id:
                    errors.append(f"{sig.id}.supersedes verweist auf unbekannte ID {target!r}")

            for signal in sig.signals:
                if signal.type not in REGEX_SIGNAL_TYPES:
                    continue
                pattern = regex_part(signal.type, signal.pattern)
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as exc:
                    errors.append(f"{sig.id}: ungültiger Regex {signal.pattern!r} ({exc})")

        if errors:
            raise SignatureError("Fehler in der Signatur-Datenbank:\n  - " + "\n  - ".join(errors))

    def get(self, signature_id: str) -> Signature | None:
        return self._by_id.get(signature_id)

    def by_role(self, *roles: Role) -> list[Signature]:
        wanted = set(roles)
        return [s for s in self.signatures if s.role in wanted]

    @property
    def platforms(self) -> list[Signature]:
        return self.by_role(Role.PLATFORM)

    @property
    def non_platforms(self) -> list[Signature]:
        return [s for s in self.signatures if s.role != Role.PLATFORM]

    def __len__(self) -> int:
        return len(self.signatures)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sig in self.signatures:
            counts[str(sig.role)] = counts.get(str(sig.role), 0) + 1
        counts["total"] = len(self.signatures)
        counts["signals"] = sum(len(s.signals) for s in self.signatures)
        return counts


def _load_file(path: Path) -> tuple[list[Signature], str]:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SignatureError(f"{path.name}: kein gültiges YAML ({exc})") from exc

    if not isinstance(raw, dict) or "signatures" not in raw:
        raise SignatureError(f"{path.name}: erwartet wird ein Mapping mit Schlüssel 'signatures'")

    version = str(raw.get("version", "unversioned"))
    signatures: list[Signature] = []

    for index, entry in enumerate(raw["signatures"] or []):
        try:
            signatures.append(Signature.model_validate(entry))
        except ValidationError as exc:
            name = entry.get("id", f"#{index}") if isinstance(entry, dict) else f"#{index}"
            raise SignatureError(f"{path.name}: Signatur {name!r} ist ungültig\n{exc}") from exc

    return signatures, version


@lru_cache(maxsize=1)
def load_registry(directory: Path | None = None) -> Registry:
    """Lädt alle YAML-Dateien aus dem Signaturverzeichnis.

    Das Ergebnis wird gecached — die Datenbank ändert sich zur Laufzeit nicht.
    """
    base = directory or SIGNATURE_DIR
    files = sorted(base.glob("*.yaml"))
    if not files:
        raise SignatureError(f"Keine Signaturdateien in {base}")

    all_signatures: list[Signature] = []
    versions: list[str] = []

    for path in files:
        signatures, version = _load_file(path)
        all_signatures.extend(signatures)
        versions.append(version)

    return Registry(all_signatures, version=max(versions))
