"""Beschaffung: alles, was das Netzwerk oder einen Browser anfasst.

Diese Schicht liefert `Observation`-Objekte und trifft keine Entscheidungen
über Anbieter. Umgekehrt darf `core` nichts hiervon importieren.
"""

from .checkout import CheckoutOutcome, simulate_checkout
from .normalize import NormalizeResult, normalize
from .render import collect_rendered
from .static import collect_static

__all__ = [
    "CheckoutOutcome",
    "NormalizeResult",
    "collect_rendered",
    "collect_static",
    "normalize",
    "simulate_checkout",
]
