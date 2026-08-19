"""Reine Erkennungslogik — kein Netzwerk, kein Browser, keine Seiteneffekte.

Diese Trennung ist die wichtigste Architekturentscheidung des Projekts.
Alles hier drin arbeitet auf `Observation`-Objekten, die serialisierbar
sind. Dadurch lässt sich die komplette Erkennung offline, deterministisch
und in Millisekunden gegen eingefrorene Fixtures prüfen — ohne je einen
echten Shop anzufassen.

`core` darf **nichts** aus `collect`, `batch` oder `api` importieren. Wird
diese Regel verletzt, verliert das Projekt seine Testbarkeit, und zwar
schleichend statt mit einem Knall.
"""

from .fuse import fuse
from .matching import match_all, match_signature
from .models import Detection, Evidence, Role, ScanResult, SignalType, Stage
from .observation import Observation
from .registry import Registry, load_registry
from .scoring import combine_weights, score_evidence

__all__ = [
    "Detection",
    "Evidence",
    "Observation",
    "Registry",
    "Role",
    "ScanResult",
    "SignalType",
    "Stage",
    "combine_weights",
    "fuse",
    "load_registry",
    "match_all",
    "match_signature",
    "score_evidence",
]
