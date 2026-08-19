"""Tests des Signalabgleichs.

Schwerpunkt liegt auf Fehlalarmen. Ein verpasster Treffer ist ärgerlich;
ein falscher Treffer untergräbt das Vertrauen in jedes andere Ergebnis.
"""

from __future__ import annotations

import pytest

from psp_radar.core.matching import host_matches, match_all, same_site
from psp_radar.core.models import Stage
from psp_radar.core.observation import Observation, extract_srcs, strip_tags
from psp_radar.core.registry import load_registry


class TestHostMatching:
    def test_exakter_treffer(self) -> None:
        assert host_matches("api.stripe.com", "api.stripe.com")

    def test_echte_subdomain_trifft(self) -> None:
        assert host_matches("eu.api.stripe.com", "api.stripe.com")

    @pytest.mark.parametrize(
        "host,pattern",
        [
            ("evilapi.stripe.com", "api.stripe.com"),
            ("notstripe.com", "stripe.com"),
            ("stripe.com.angreifer.de", "stripe.com"),
            ("meinstripe.com", "stripe.com"),
            ("fake-adyen.com", "adyen.com"),
        ],
    )
    def test_beinahetreffer_werden_abgelehnt(self, host: str, pattern: str) -> None:
        """Die häufigste Ursache für Fehlalarme in solchen Tools."""
        assert not host_matches(host, pattern), f"{host} darf nicht als {pattern} gelten"

    def test_wildcard_praefix_wird_normalisiert(self) -> None:
        assert host_matches("checkout.stripe.com", "*.stripe.com")

    def test_gross_klein_egal(self) -> None:
        assert host_matches("API.Stripe.COM", "api.stripe.com")


class TestCspExtraktion:
    def test_hosts_aus_csp_werden_gefunden(self) -> None:
        obs = Observation(
            stage=Stage.STATIC,
            source_url="https://shop.de",
            headers={
                "content-security-policy": (
                    "default-src 'self'; "
                    "frame-src https://*.adyen.com https://js.stripe.com; "
                    "connect-src 'self' https://checkoutshopper-live.adyen.com"
                )
            },
        )
        obs.merge_csp_from_headers()
        assert "*.adyen.com" in obs.csp_domains or any(
            "adyen.com" in d for d in obs.csp_domains
        )
        assert any("stripe.com" in d for d in obs.csp_domains)

    def test_keine_csp_ist_kein_fehler(self) -> None:
        obs = Observation(stage=Stage.STATIC, source_url="https://shop.de")
        obs.merge_csp_from_headers()
        assert obs.csp_domains == []

    def test_report_only_wird_mitgelesen(self) -> None:
        obs = Observation(
            stage=Stage.STATIC,
            source_url="https://shop.de",
            headers={"content-security-policy-report-only": "connect-src https://api.unzer.com"},
        )
        obs.merge_csp_from_headers()
        assert any("unzer.com" in d for d in obs.csp_domains)


class TestSignalabgleich:
    def test_stripe_live_key_wird_erkannt(self) -> None:
        obs = Observation(
            stage=Stage.STATIC,
            source_url="https://shop.de",
            html="<script>Stripe('pk_live_51H8xKjLmNoPqRsTuVwXyZ123')</script>",
        )
        evidence = match_all(load_registry(), [obs])
        assert "stripe" in evidence
        assert max(e.weight for e in evidence["stripe"]) >= 95

    def test_testkey_wiegt_deutlich_weniger_als_livekey(self) -> None:
        """Ein Testkey bedeutet: Integration existiert, ist aber evtl. nicht scharf."""
        registry = load_registry()
        stripe = registry.get("stripe")
        assert stripe is not None
        live = next(s for s in stripe.signals if "pk_live" in s.pattern)
        test = next(s for s in stripe.signals if "pk_test" in s.pattern)
        assert live.weight - test.weight >= 40

    def test_unzer_ueber_netzwerkhost(self) -> None:
        obs = Observation(
            stage=Stage.CHECKOUT,
            source_url="https://shop.de/checkout",
            network_urls=["https://api.unzer.com/v1/payments", "https://cdn.shop.de/app.js"],
        )
        evidence = match_all(load_registry(), [obs])
        assert "unzer" in evidence

    def test_leere_observation_erzeugt_keine_evidenz(self) -> None:
        obs = Observation(stage=Stage.STATIC, source_url="https://shop.de")
        assert match_all(load_registry(), [obs]) == {}

    def test_requires_platform_filtert_korrekt(self) -> None:
        """Shopify Payments darf ohne Shopify-Plattform nicht anschlagen."""
        obs = Observation(
            stage=Stage.CHECKOUT,
            source_url="https://shop.de/checkout",
            network_urls=["https://deposit.shopifycs.com/sessions"],
        )
        registry = load_registry()

        ohne = match_all(registry, [obs], detected_platform=None)
        assert "shopify_payments" not in ohne

        mit = match_all(registry, [obs], detected_platform="shopify")
        assert "shopify_payments" in mit

    def test_harmloser_shop_loest_keinen_psp_aus(self) -> None:
        """Regressionsschutz gegen zu gierige Signaturen."""
        obs = Observation(
            stage=Stage.STATIC,
            source_url="https://blog.de",
            html="<html><body><h1>Willkommen</h1><p>Ein Blog über Zahlungen und Stripe.</p></body></html>",
            dom_text="Willkommen Ein Blog über Zahlungen und Stripe.",
        )
        evidence = match_all(load_registry(), [obs])
        assert "stripe" not in evidence, "Blosse Erwähnung im Text darf nicht triggern"


class TestHilfsfunktionen:
    def test_script_und_iframe_extraktion(self) -> None:
        html = """
        <script src="https://js.stripe.com/v3/"></script>
        <script src='/local.js'></script>
        <iframe src="https://checkout.stripe.com/x"></iframe>
        """
        scripts, iframes = extract_srcs(html)
        assert "https://js.stripe.com/v3/" in scripts
        assert "/local.js" in scripts
        assert "https://checkout.stripe.com/x" in iframes

    def test_strip_tags_entfernt_skripte(self) -> None:
        text = strip_tags("<div>Hallo<script>var geheim=1;</script>Welt</div>")
        assert "Hallo" in text and "Welt" in text
        assert "geheim" not in text

    def test_same_site(self) -> None:
        assert same_site("https://shop.de/a", "https://shop.de/b")
        assert same_site("https://www.shop.de", "https://shop.de")
        assert not same_site("https://shop.de", "https://anderer.de")
