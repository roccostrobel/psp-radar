"""Tests der Fusion — dort, wo aus Evidenz ein Urteil wird.

Der interessanteste Teil, weil hier die Fehler entstehen, die man als
Nutzer nicht bemerkt: ein plausibel klingendes, aber falsch zugeordnetes
Ergebnis.
"""

from __future__ import annotations

from psp_radar.core.models import Stage
from psp_radar.core.observation import Observation
from psp_radar.eval.golden import evaluate_observations


def obs(stage: Stage = Stage.CHECKOUT, **kwargs: object) -> Observation:
    return Observation(stage=stage, source_url="https://shop.de/checkout", **kwargs)  # type: ignore[arg-type]


class TestRollentrennung:
    def test_paypal_landet_bei_zahlungsarten_nicht_bei_psp(self) -> None:
        """Der wichtigste Test des Projekts.

        Ein Shop mit PayPal-Button und Stripe im Hintergrund: PayPal ist
        die Zahlungsart, Stripe der Abwickler. Wer beides in einen Topf
        wirft, produziert unbrauchbare Marktdaten.
        """
        result = evaluate_observations(
            [
                obs(
                    network_urls=[
                        "https://www.paypal.com/sdk/js?client-id=abc",
                        "https://api.stripe.com/v1/payment_intents",
                        "https://js.stripe.com/v3/",
                    ]
                )
            ]
        )

        psp_ids = {d.id for d in result.psps}
        wallet_ids = {d.id for d in result.wallets}

        assert "stripe" in psp_ids
        assert "paypal" in wallet_ids
        assert "paypal" not in psp_ids
        assert result.primary_psp is not None
        assert result.primary_psp.id == "stripe"

    def test_klarna_ist_zahlungsart(self) -> None:
        result = evaluate_observations(
            [obs(network_urls=["https://api.klarna.com/payments/v1/sessions"])]
        )
        assert "klarna" in {d.id for d in result.payment_methods}
        assert "klarna" not in {d.id for d in result.psps}

    def test_fraud_tools_getrennt_gefuehrt(self) -> None:
        result = evaluate_observations(
            [obs(network_urls=["https://beacon.riskified.com/v1/beacon"])]
        )
        assert "riskified" in {d.id for d in result.fraud_tools}
        assert "riskified" not in {d.id for d in result.psps}


class TestKonfliktaufloesung:
    def test_shopify_payments_verdraengt_stripe(self) -> None:
        """Beide zu melden wäre nicht falsch, aber irreführend.

        Der Traffic geht an Stripe-Infrastruktur; Vertragspartner des
        Händlers ist aber Shopify. Stripe gehört ins Feld `underlying`,
        nicht in die Ergebnisliste.
        """
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.STATIC,
                    html='<script>Shopify.shop = "test.myshopify.com";</script>',
                    headers={"x-shopid": "12345"},
                    network_urls=["https://cdn.shopify.com/s/files/1/app.js"],
                ),
                obs(
                    network_urls=[
                        "https://deposit.shopifycs.com/sessions",
                        "https://api.stripe.com/v1/tokens",
                    ]
                ),
            ]
        )

        assert result.platform is not None
        assert result.platform.id == "shopify"

        psp_ids = {d.id for d in result.psps}
        assert "shopify_payments" in psp_ids
        assert "stripe" not in psp_ids, "Stripe soll als underlying geführt werden"

        primary = result.primary_psp
        assert primary is not None
        assert primary.underlying == "stripe"


class TestConfidenceVerhalten:
    def test_ohne_checkout_wird_gedeckelt(self) -> None:
        """Wer den Checkout nicht gesehen hat, darf keine Gewissheit behaupten."""
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.STATIC,
                    html="<script>Stripe('pk_live_51H8xKjLmNoPqRsTuVwXyZ123')</script>",
                )
            ]
        )
        assert not result.checkout_reached
        assert result.overall_confidence <= 82

    def test_mit_checkout_volle_confidence_moeglich(self) -> None:
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.CHECKOUT,
                    html="<script>Stripe('pk_live_51H8xKjLmNoPqRsTuVwXyZ123')</script>",
                    network_urls=["https://api.stripe.com/v1/payment_intents"],
                )
            ]
        )
        assert result.checkout_reached
        assert result.overall_confidence >= 90

    def test_kein_fund_erzeugt_ehrliche_warnung(self) -> None:
        """Schweigen mit Begründung statt Raten."""
        result = evaluate_observations(
            [obs(stage=Stage.STATIC, html="<html><body>Nichts hier</body></html>")]
        )
        assert result.primary_psp is None
        assert result.overall_confidence == 0
        assert any(w.code == "no_psp_found" for w in result.warnings)

    def test_checkout_ohne_psp_wird_als_signaturluecke_gemeldet(self) -> None:
        """Der Hinweis, der die Signatur-Datenbank wachsen lässt."""
        result = evaluate_observations(
            [obs(stage=Stage.CHECKOUT, network_urls=["https://unbekannter-psp.example/pay"])]
        )
        assert any(w.code == "checkout_without_psp" for w in result.warnings)


class TestPlattformerkennung:
    def test_nur_eine_plattform_wird_gemeldet(self) -> None:
        """Ein Shop läuft auf einem System. Mehrere Treffer sind Rauschen."""
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.STATIC,
                    html=(
                        '<script>Shopify.shop = "x";</script>'
                        '<link href="/wp-content/plugins/woocommerce/style.css">'
                    ),
                    headers={"x-shopid": "999"},
                )
            ]
        )
        assert result.platform is not None
        assert result.platform.id == "shopify"

    def test_shopware_wird_erkannt(self) -> None:
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.STATIC,
                    html='<script src="/bundles/storefront/js/app.js"></script>',
                    headers={"sw-invalidation-states": "logged-in"},
                )
            ]
        )
        assert result.platform is not None
        assert result.platform.id == "shopware"


class TestAusgabe:
    def test_summary_line_ohne_psp(self) -> None:
        result = evaluate_observations([obs(stage=Stage.STATIC, html="<html></html>")])
        assert "unbekannt" in result.summary_line()

    def test_json_export_ist_vollstaendig(self) -> None:
        import json

        result = evaluate_observations(
            [obs(network_urls=["https://api.stripe.com/v1/payment_intents"])]
        )
        data = json.loads(result.model_dump_json())
        assert data["psps"][0]["id"] == "stripe"
        assert data["psps"][0]["evidence"], "Belege müssen im Export enthalten sein"

    def test_confidence_label_landet_im_json(self) -> None:
        """Regressionsschutz für einen Fehler, der in Python unsichtbar war.

        `confidence_label` war eine gewöhnliche @property. In Python las sie
        sich korrekt, pydantic serialisiert Properties aber nicht — der
        Weboberfläche fehlte damit die Einstufung, und die farbige
        Kennzeichnung blieb stumm. Auffällig wurde es erst im Browser.
        """
        import json

        result = evaluate_observations(
            [obs(network_urls=["https://api.stripe.com/v1/payment_intents"])]
        )
        payload = json.loads(result.model_dump_json())["psps"][0]

        assert "confidence_label" in payload
        assert payload["confidence_label"] in ("sicher", "wahrscheinlich", "moeglich", "schwach")
        assert "evidence_count" in payload
        assert payload["evidence_count"] == len(payload["evidence"])

    def test_unterbau_wird_mit_anzeigename_ausgegeben(self) -> None:
        """`underlying` ist eine Signatur-ID — für Menschen braucht es den Namen."""
        result = evaluate_observations(
            [
                obs(
                    stage=Stage.STATIC,
                    headers={"x-shopid": "12345"},
                    html='<script>Shopify.shop = "x";</script>',
                ),
                obs(network_urls=["https://deposit.shopifycs.com/sessions"]),
            ]
        )
        primary = result.primary_psp
        assert primary is not None
        assert primary.underlying == "stripe"
        assert primary.underlying_name == "Stripe"
