"""Sicherheitstests — der wichtigste Testfile im Projekt.

Das Tool klickt sich durch fremde Checkouts. Wenn hier etwas durchrutscht,
löst es echte Bestellungen bei echten Händlern aus. Diese Tests sind
deshalb bewusst paranoid und decken auch Schreibweisen ab, die im
Produktivcode gar nicht vorkommen sollten.
"""

from __future__ import annotations

import pytest

from psp_radar.collect.adapters.base import is_forbidden_label

# Beschriftungen, die eine Bestellung auslösen könnten. Keine davon
# darf jemals geklickt werden.
MUST_BLOCK = [
    "Zahlungspflichtig bestellen",
    "zahlungspflichtig bestellen",
    "ZAHLUNGSPFLICHTIG BESTELLEN",
    "Jetzt bestellen",
    "Jetzt kaufen",
    "Kaufen",
    "Zahlungspflichtig Bestellen »",
    "Bestellung abschließen",
    "Bestellung abschliessen",
    "Kostenpflichtig bestellen",
    "Place order",
    "Place Order",
    "Complete order",
    "Order now",
    "Pay now",
    "Buy now",
    "Confirm and pay",
    "Confirm & Pay",
    "Submit order",
    "  Jetzt   bestellen  ",
    "Weiter und zahlungspflichtig bestellen",
    "Zahlungspflichtig buchen",
    "Bestellung absenden",
    "Bestellung aufgeben",
    "Verbindlich bestellen",
    "Complete purchase",
    "Purchase now",
]

# Beschriftungen, die geklickt werden dürfen — sie bringen uns zur
# Zahlungsauswahl, lösen aber nichts aus.
MUST_ALLOW = [
    "In den Warenkorb",
    "Zur Kasse",
    "Weiter",
    "Weiter zur Zahlung",
    "Zur Zahlungsart",
    "Als Gast bestellen",
    "Continue to payment",
    "Add to cart",
    "Alle akzeptieren",
    "Weiter zur Übersicht",
    "Versandart wählen",
]


@pytest.mark.parametrize("label", MUST_BLOCK)
def test_kaufausloesende_labels_werden_blockiert(label: str) -> None:
    assert is_forbidden_label(label), f"GEFAHR: {label!r} würde geklickt werden"


@pytest.mark.parametrize("label", MUST_ALLOW)
def test_harmlose_labels_bleiben_erlaubt(label: str) -> None:
    assert not is_forbidden_label(label), f"{label!r} wird unnötig blockiert"


def test_gast_bestellen_ist_erlaubt_aber_jetzt_bestellen_nicht() -> None:
    """Der Unterschied zwischen 'Als Gast bestellen' und 'Jetzt bestellen'.

    Beide enthalten 'bestellen'. Nur eines davon kostet Geld. Eine naive
    Substring-Prüfung auf 'bestellen' würde entweder zu viel blockieren
    oder zu wenig — deshalb wird auf Phrasen geprüft, nicht auf Wörter.
    """
    assert not is_forbidden_label("Als Gast bestellen")
    assert is_forbidden_label("Jetzt bestellen")
    assert is_forbidden_label("Bestellung abschließen")


def test_sperrliste_ist_nicht_leer() -> None:
    """Schutz davor, dass die Sperrliste versehentlich geleert wird."""
    from psp_radar.config import FORBIDDEN_SUBMIT_PATTERNS

    assert len(FORBIDDEN_SUBMIT_PATTERNS) >= 10


def test_leeres_label_wird_nicht_als_harmlos_gewertet() -> None:
    """Ein Element ohne lesbaren Text darf nicht automatisch als sicher gelten.

    is_forbidden_label liefert hier False — der Schutz greift eine Ebene
    höher in safe_click, das ohne ermittelbaren Text gar nicht erst klickt.
    Dieser Test hält den Zusammenhang fest, damit er nicht verloren geht.
    """
    import inspect

    from psp_radar.collect.adapters.base import safe_click

    source = inspect.getsource(safe_click)
    assert "is_forbidden_label" in source
    assert "except PlaywrightError:\n        return False" in source
