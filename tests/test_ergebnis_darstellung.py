"""Tests der Ergebnisdarstellung — die Belegart gehört neben die Zahl.

Hintergrund ist eine Messung, nicht eine Designvorliebe. Über 15 DACH-Shops
ist der Abwickler ohne Checkout-Beobachtung nur bei etwa einem Viertel
bestimmbar (`docs/BEFUNDE.md`). Eine Prozentzahl allein verschweigt den
Unterschied, auf den es dabei ankommt:

- Ein im Checkout beobachteter Request an die Zahlungs-API ist ein Beweis.
- Ein Satz auf der Seite "Lieferung und Zahlung" ist eine Aussage des
  Händlers über sich selbst — belastbar, aber keine Beobachtung.
- Ein Host auf der Startseite ist ein Indiz.

Alle drei können 92 % ergeben. Deshalb trägt jedes Ergebnis seine Herkunft.
"""

from __future__ import annotations

import json

from psp_radar.core.models import (
    Detection,
    Evidence,
    Role,
    ScanResult,
    ScanWarning,
    SignalType,
    Stage,
)
from psp_radar.report import CSV_COLUMNS, result_to_row


def _beleg(signal: SignalType, stage: Stage, weight: int = 80) -> Evidence:
    return Evidence(
        signature_id="unzer",
        signal_type=signal,
        pattern="unzer\\.com",
        matched_value="secure.unzer.com",
        weight=weight,
        stage=stage,
    )


def _ergebnis(*belege: Evidence, checkout: bool = False, warnungen: list[str] | None = None) -> ScanResult:
    treffer = (
        [
            Detection(
                id="unzer",
                name="Unzer",
                role=Role.GATEWAY,
                confidence=92,
                evidence=list(belege),
            )
        ]
        if belege
        else []
    )
    return ScanResult(
        url="https://shop.de",
        psps=treffer,
        checkout_reached=checkout,
        warnings=[ScanWarning(code=c, message=c) for c in (warnungen or [])],
    )


class TestBelegart:
    def test_checkout_beobachtung_ist_die_staerkste_aussage(self) -> None:
        ergebnis = _ergebnis(
            _beleg(SignalType.NETWORK_HOST, Stage.CHECKOUT), checkout=True
        )
        assert ergebnis.acquirer_source == "beobachtet"
        assert "beobachtet" in ergebnis.acquirer_note

    def test_haendlerangabe_gilt_als_angegeben_nicht_als_beobachtet(self) -> None:
        """Der Unterschied, den bergfreunde.de sichtbar macht.

        Dort steht Unzer im Text der Zahlungsseite, während die
        Checkout-Simulation weiterhin scheitert. 92 % sind gerechtfertigt —
        aber es ist eine Aussage des Händlers, keine Messung des Datenverkehrs.
        """
        ergebnis = _ergebnis(_beleg(SignalType.PAYMENT_PAGE_TEXT, Stage.STATIC, 72))
        assert ergebnis.acquirer_source == "angegeben"
        assert "nicht im Checkout beobachtet" in ergebnis.acquirer_note

    def test_indirekte_spuren_werden_als_vermutung_gekennzeichnet(self) -> None:
        ergebnis = _ergebnis(_beleg(SignalType.NETWORK_HOST, Stage.RENDER, 55))
        assert ergebnis.acquirer_source == "vermutet"
        assert "indirekte Spuren" in ergebnis.acquirer_note

    def test_ohne_treffer_keine_quelle(self) -> None:
        assert _ergebnis().acquirer_source == "keine"

    def test_checkout_stufe_schlaegt_zahlungsseitentext(self) -> None:
        """Bei zwei Belegen gilt der stärkere."""
        ergebnis = _ergebnis(
            _beleg(SignalType.PAYMENT_PAGE_TEXT, Stage.STATIC, 72),
            _beleg(SignalType.NETWORK_HOST, Stage.CHECKOUT, 95),
            checkout=True,
        )
        assert ergebnis.acquirer_source == "beobachtet"


class TestBegruendungBeiFehlschlag:
    """Die Unterscheidung, deren Fehlen im Vorgänger in die Irre führte.

    Dort meldete das Tool bei kaputtem Adapter "Signatur fehlt vermutlich".
    Wer dem folgte, erweiterte die Signaturdatenbank, während in Wahrheit
    das Produkt nie im Warenkorb landete.
    """

    def test_leerer_warenkorb_zeigt_auf_die_selektoren(self) -> None:
        note = _ergebnis(warnungen=["checkout_cart_empty"]).acquirer_note
        assert "Selektoren" in note
        assert "nicht fehlende Signaturen" in note, (
            "Die Begründung muss die falsche Fährte ausdrücklich ausschliessen. "
            "Genau ihr ist der Vorgänger gefolgt."
        )

    def test_erreichter_checkout_ohne_treffer_zeigt_auf_die_signaturen(self) -> None:
        note = _ergebnis(checkout=True).acquirer_note
        assert "Signatur" in note

    def test_fehlende_zahlungsseite_wird_benannt(self) -> None:
        note = _ergebnis(warnungen=["no_payment_page"]).acquirer_note
        assert "Zahlungsseite" in note

    def test_ohne_hinweise_bleibt_die_ehrliche_grundaussage(self) -> None:
        note = _ergebnis().acquirer_note
        assert "nach der" in note and "Zahlungsauswahl" in note


class TestSerialisierung:
    def test_belegart_landet_im_json(self) -> None:
        """Sonst sieht die Oberfläche sie nicht.

        Genau dieser Fehler ist in diesem Projekt schon einmal passiert:
        `confidence_label` war ein einfaches `@property` und fehlte deshalb
        im JSON. In Python funktionierte alles, in der Oberfläche blieb die
        Einstufung leer — und beim Lesen des Codes fällt das nicht auf.
        """
        ergebnis = _ergebnis(_beleg(SignalType.NETWORK_HOST, Stage.CHECKOUT), checkout=True)
        daten = json.loads(ergebnis.model_dump_json())

        assert daten["acquirer_source"] == "beobachtet"
        assert daten["acquirer_note"]

    def test_csv_fuehrt_die_quelle_als_eigene_spalte(self) -> None:
        assert "psp_quelle" in CSV_COLUMNS
        zeile = result_to_row(
            _ergebnis(_beleg(SignalType.PAYMENT_PAGE_TEXT, Stage.STATIC, 72))
        )
        assert zeile["psp_quelle"] == "angegeben"
        assert set(zeile) == set(CSV_COLUMNS), "Zeile und Kopfzeile müssen deckungsgleich sein"


class TestOberflaeche:
    """Die Oberfläche liest Felder, die es geben muss."""

    def test_template_nutzt_die_gelieferten_felder(self) -> None:
        from psp_radar.web import template

        quelltext = template._JS if hasattr(template, "_JS") else ""
        if not quelltext:  # Feldname kann sich ändern, dann alles prüfen
            quelltext = "\n".join(
                str(v) for k, v in vars(template).items() if isinstance(v, str) and not k.startswith("__")
            )

        assert "acquirer_source" in quelltext
        assert "acquirer_note" in quelltext

    def test_versprochene_felder_existieren_am_modell(self) -> None:
        """Wächter gegen den Vertragsbruch zwischen Modell und Oberfläche."""
        felder = set(json.loads(_ergebnis().model_dump_json()))
        assert {"acquirer_source", "acquirer_note", "tier", "checkout_reached"} <= felder
