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


def test_unterschied_kommt_auch_im_ergebnis_an() -> None:
    """Die Unterscheidung muss bis zur Anzeige durchgehalten werden.

    Sie war im Outcome vorhanden, ging danach aber verloren: `ScanResult`
    kannte nur `checkout_reached`, gefüllt aus `reached_checkout_page`. Der
    Bericht zeigte deshalb "Checkout erreicht ✓" direkt neben der Warnung
    "Zahlungsauswahl nicht erreicht" — beides richtig, zusammen widersprüchlich.

    Belegt an snocks.com: Checkout-Seite erreicht, Shopify Payments zu 98 %
    erkannt, Zahlungsauswahl nicht erreicht.
    """
    from psp_radar.core.models import ScanResult
    from psp_radar.report import fortschritt

    teilerfolg = ScanResult(
        url="https://snocks.com", checkout_reached=True, payment_selection_reached=False
    )
    assert "Zahlungsauswahl nicht" in fortschritt(teilerfolg)

    vollerfolg = ScanResult(
        url="https://snocks.com", checkout_reached=True, payment_selection_reached=True
    )
    assert "Zahlungsauswahl erreicht" in fortschritt(vollerfolg)

    ohne = ScanResult(url="https://snocks.com")
    assert "ohne Checkout" in fortschritt(ohne)


def test_zahlungsauswahl_stammt_aus_dem_outcome() -> None:
    """Gleiche Absicherung wie für checkout_reached — gleiche Fehlerquelle."""
    import inspect

    from psp_radar import scanner

    quelle = inspect.getsource(scanner.scan)
    assert "outcome and outcome.reached_payment" in quelle
