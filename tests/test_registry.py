"""Tests der Signatur-Datenbank.

Diese Tests laufen bei jeder Änderung an den YAML-Dateien mit. Ein
Tippfehler in einer Referenz oder ein kaputter Regex würde sonst
stillschweigend dazu führen, dass eine Regel nie greift — der
unangenehmste Fehlertyp, weil er wie ein normales Negativergebnis aussieht.
"""

from __future__ import annotations

import re

from psp_radar.core.models import REGEX_SIGNAL_TYPES, Role
from psp_radar.core.registry import load_registry, regex_part


def test_datenbank_laedt_ohne_fehler() -> None:
    registry = load_registry()
    assert len(registry) > 40


def test_alle_ids_eindeutig() -> None:
    registry = load_registry()
    ids = [s.id for s in registry.signatures]
    assert len(ids) == len(set(ids))


def test_alle_regexe_kompilieren() -> None:
    """Nur regexbasierte Signaltypen prüfen.

    Ein Hostmuster wie `*.stripe.com` ist bewusst kein regulärer Ausdruck
    und würde beim Kompilieren zu Recht scheitern.
    """
    for signature in load_registry().signatures:
        for signal in signature.signals:
            if signal.type not in REGEX_SIGNAL_TYPES:
                continue
            re.compile(regex_part(signal.type, signal.pattern), re.IGNORECASE)


def test_gewichte_im_gueltigen_bereich() -> None:
    for signature in load_registry().signatures:
        for signal in signature.signals:
            assert 1 <= signal.weight <= 100, f"{signature.id}: Gewicht {signal.weight}"


def test_jede_signatur_hat_mindestens_ein_starkes_signal() -> None:
    """Eine Signatur nur aus schwachen Indizien kann nie sicher auslösen.

    Solche Einträge sind entweder unfertig oder erzeugen Rauschen —
    beides soll auffallen, bevor es im Ergebnis landet.
    """
    schwach: list[str] = []
    for signature in load_registry().signatures:
        if max(s.weight for s in signature.signals) < 70:
            schwach.append(signature.id)
    assert not schwach, f"Signaturen ohne belastbares Signal: {schwach}"


def test_dach_anbieter_sind_abgedeckt() -> None:
    """Kernversprechen des Projekts: der deutschsprachige Markt sitzt."""
    registry = load_registry()
    pflicht = {
        "unzer",
        "computop",
        "payone",
        "novalnet",
        "datatrans",
        "saferpay",
        "stripe",
        "adyen",
        "mollie",
        "klarna",
        "paypal",
    }
    fehlend = pflicht - {s.id for s in registry.signatures}
    assert not fehlend, f"Fehlende Signaturen: {fehlend}"


def test_dach_shopsysteme_sind_abgedeckt() -> None:
    registry = load_registry()
    pflicht = {"shopware", "jtl_shop", "oxid", "plentymarkets", "gambio", "woocommerce", "shopify"}
    fehlend = pflicht - {s.id for s in registry.platforms}
    assert not fehlend, f"Fehlende Shop-Systeme: {fehlend}"


def test_rollen_sind_sinnvoll_verteilt() -> None:
    registry = load_registry()
    stats = registry.stats()
    assert stats[str(Role.GATEWAY)] >= 15
    assert stats[str(Role.PLATFORM)] >= 10
    assert stats[str(Role.METHOD)] >= 5


def test_paypal_ist_wallet_kein_gateway() -> None:
    """Die zentrale Unterscheidung des Modells, hier festgeschrieben.

    Ein PayPal-Button sagt nichts darüber aus, wer die Kartenzahlung
    abwickelt. Wird PayPal je zum Gateway umdeklariert, schlägt dieser
    Test an — und das soll er.
    """
    paypal = load_registry().get("paypal")
    assert paypal is not None
    assert paypal.role == Role.WALLET


def test_shopify_payments_verdraengt_stripe() -> None:
    """Shopify Payments läuft technisch auf Stripe, wird aber von Shopify abgerechnet."""
    signature = load_registry().get("shopify_payments")
    assert signature is not None
    assert signature.underlying == "stripe"
    assert "stripe" in signature.supersedes
    assert signature.requires_platform == "shopify"


def test_testumgebungen_wiegen_weniger_als_produktiv() -> None:
    """Ein Sandbox-Host beweist keine laufende Zahlungsabwicklung."""
    registry = load_registry()
    adyen = registry.get("adyen")
    assert adyen is not None
    live = next(s for s in adyen.signals if "checkoutshopper-live" in s.pattern)
    test = next(s for s in adyen.signals if "checkoutshopper-test" in s.pattern)
    assert live.weight > test.weight + 30


def test_dom_text_signale_sind_schwach() -> None:
    """Sichtbarer Text ist Marketing, kein technischer Beleg."""
    for signature in load_registry().signatures:
        for signal in signature.signals:
            if signal.type == "dom_text":
                assert signal.weight <= 25, f"{signature.id}: dom_text mit Gewicht {signal.weight}"
