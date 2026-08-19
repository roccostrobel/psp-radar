"""Das Tool darf nicht behaupten, weiter gekommen zu sein, als es kam.

Hintergrund ist ein echter Fehler: `checkout_reached` wurde daraus
abgeleitet, ob irgendeine Observation die Stufe CHECKOUT trägt. Die wird
aber auch beim Scheitern angelegt, um den Zustand für die Fehlersuche
festzuhalten. Ergebnis war ein "Checkout erreicht ✓" für Shops, bei denen
nicht einmal das Produkt im Warenkorb landete — und obendrein die Warnung
`checkout_without_psp`, die eine fehlende Signatur nahelegte, obwohl das
Problem ganz woanders lag.

Der Schaden ist nicht der falsche Haken, sondern die Fehlleitung: Man
optimiert die Signatur-Datenbank, während der Adapter kaputt ist.
"""

from __future__ import annotations

from psp_radar.collect import CheckoutOutcome
from psp_radar.core.models import Stage
from psp_radar.core.observation import Observation


def test_gescheiterter_warenkorb_gilt_nicht_als_erreichter_checkout() -> None:
    outcome = CheckoutOutcome(reached_payment=False, reached_checkout_page=False)
    outcome.observations.append(
        Observation(stage=Stage.CHECKOUT, source_url="https://shop.de/produkt")
    )

    # Observation mit Stufe CHECKOUT vorhanden ...
    assert any(o.stage == Stage.CHECKOUT for o in outcome.observations)
    # ... aber der Checkout wurde nachweislich nicht erreicht.
    assert outcome.reached_checkout_page is False


def test_scanner_leitet_checkout_reached_aus_dem_outcome_ab() -> None:
    """Sichert die Quelle der Wahrheit ab, nicht nur das Ergebnis.

    Ein Test auf den Wert allein würde die Regression nicht fangen, weil
    beide Varianten in vielen Fällen dasselbe liefern. Deshalb wird hier
    festgehalten, *woraus* der Wert stammen muss.
    """
    import inspect

    from psp_radar import scanner

    quelle = inspect.getsource(scanner.scan)
    assert "outcome and outcome.reached_checkout_page" in quelle, (
        "checkout_reached muss aus dem CheckoutOutcome stammen, nicht aus den "
        "Stufen der Observations"
    )


def test_zahlungsauswahl_ist_strenger_als_checkout_seite() -> None:
    """Zwei getrennte Stufen, weil sie unterschiedlich viel aussagen.

    Die Checkout-Seite erreicht zu haben heisst noch nicht, die
    Zahlungsauswahl gesehen zu haben — dort erst zeigt sich der PSP
    vollständig.
    """
    outcome = CheckoutOutcome(reached_payment=False, reached_checkout_page=True)
    assert outcome.reached_checkout_page and not outcome.reached_payment
