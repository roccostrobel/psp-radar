"""Messung der Erkennungsgüte und der Laufzeit.

Ohne diese Schicht wäre die Vorgabe "schneller, aber ohne Qualitätsverlust"
nicht überprüfbar — und damit eine Behauptung statt einer Aussage.
"""

from .golden import Metrics, load_golden, run_evaluation

__all__ = ["Metrics", "load_golden", "run_evaluation"]
