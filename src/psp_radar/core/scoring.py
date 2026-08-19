"""Verdichtung von Evidenz zu Confidence-Werten.

Warum nicht einfach addieren? Weil Addition lügt. Fünf schwache Indizien
ergäben 5 x 20 = 100 und damit scheinbare Gewissheit, obwohl kein einziges
davon belastbar ist. Genau so entstehen Tools, denen man nicht trauen kann.

Stattdessen: Noisy-OR mit Dämpfung.

  - Noisy-OR:  p = 1 - Π(1 - wᵢ)   — Signale stützen sich, sprengen aber
    nie die 100er-Grenze.
  - Dämpfung:  jedes weitere Signal zählt um den Faktor DECAY weniger.
    Das verhindert, dass viele schwache, oft korrelierte Signale
    (dasselbe SDK, dreimal anders gesehen) falsche Sicherheit erzeugen.

Ergebnis: Ein einzelner harter Treffer (Live-Key im Quelltext, Request an
die PSP-API) reicht allein. Viele weiche Treffer landen ehrlich im
Bereich "wahrscheinlich" statt bei "sicher".
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import Evidence

#: Jedes weitere Signal wird mit diesem Faktor abgeschwächt.
#: 0.85 ist bewusst konservativ gewählt und über das Golden-Set kalibrierbar.
DECAY = 0.85

#: Ab dieser Confidence gilt ein Ergebnis als belastbar genug, um die
#: teure Checkout-Simulation zu überspringen (Modus --auto-depth).
SKIP_CHECKOUT_THRESHOLD = 92

#: Unterhalb dieser Confidence wird ein Fund nicht mehr berichtet.
REPORT_FLOOR = 25


def combine_weights(weights: Iterable[int], decay: float = DECAY) -> int:
    """Führt Einzelgewichte zu einer Gesamt-Confidence 0-100 zusammen.

    Die Gewichte werden absteigend sortiert, damit das stärkste Signal
    ungedämpft zählt und nur die Stützsignale abgeschwächt werden.

    >>> combine_weights([99])
    99
    >>> combine_weights([20, 20, 20, 20, 20])
    55
    >>> combine_weights([95, 88])
    99
    >>> combine_weights([])
    0
    """
    ordered = sorted((w for w in weights if w > 0), reverse=True)
    if not ordered:
        return 0

    p_none = 1.0
    for index, weight in enumerate(ordered):
        effective = (weight / 100.0) * (decay**index)
        p_none *= 1.0 - effective

    return round((1.0 - p_none) * 100)


def dedupe(evidence: Iterable[Evidence]) -> list[Evidence]:
    """Entfernt mehrfach gefundene identische Signale.

    Ein Stripe-Skript, das auf Startseite, Produktseite und im Checkout
    auftaucht, ist *ein* Indiz, nicht drei. Behalten wird der Fund aus der
    aussagekräftigsten Stufe (Checkout schlägt Render schlägt Static).
    """
    stage_rank = {"checkout": 3, "render": 2, "static": 1, "normalize": 0}
    best: dict[tuple[str, str, str], Evidence] = {}

    for item in evidence:
        key = item.dedup_key()
        current = best.get(key)
        if current is None or stage_rank.get(str(item.stage), 0) > stage_rank.get(
            str(current.stage), 0
        ):
            best[key] = item

    return sorted(best.values(), key=lambda e: (-e.weight, e.signature_id))


def score_evidence(evidence: Iterable[Evidence]) -> tuple[int, list[Evidence]]:
    """Berechnet die Confidence für *eine* Signatur aus ihrer Evidenz.

    Gibt zusätzlich die entdoppelte, nach Gewicht sortierte Evidenzliste
    zurück — die gehört in den Report, damit jeder Wert prüfbar bleibt.
    """
    unique = dedupe(evidence)
    return combine_weights(e.weight for e in unique), unique


def checkout_bonus(score: int, reached_checkout: bool) -> int:
    """Wertet Evidenz auf, die tatsächlich im Checkout beobachtet wurde.

    Ein Gateway, das im echten Checkout Traffic erzeugt, ist praktisch
    bewiesen — dort läuft die Zahlung. Derselbe Host auf der Startseite
    könnte auch ein Überbleibsel oder ein Analytics-Skript sein.
    """
    if not reached_checkout:
        return score
    return min(100, round(score + (100 - score) * 0.5))
