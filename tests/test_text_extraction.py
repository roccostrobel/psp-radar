"""Tests des Textauszugs — der Fehler, der die Erkennung stumm machte.

Die erste Fassung von `strip_tags` schnitt das **HTML** bei 200.000 Zeichen
ab und entfernte erst danach die Tags. Bei bergfreunde.de hat die Seite
"Lieferung und Zahlung" 873.504 Zeichen HTML; die ersten 200.000 sind fast
ausschliesslich Skripte und eingebettetes JSON. Übrig blieben **103 Zeichen**
sichtbarer Text.

Der Satz "Die Abwicklung des Zahlungsprozesses erfolgt dann über den
Dienstleister Payolution/Unzer" lag weit dahinter. Das Tool meldete "kein
Zahlungsdienstleister erkannt", während die Antwort im Quelltext stand — die
unangenehmste Fehlerart, weil das Ergebnis plausibel aussieht.

Nach der Korrektur: 15.130 Zeichen Text, Unzer mit 92 % erkannt, in 12
Sekunden ohne Browser.

Der Fehler betraf **jeden** grossen Shop. Text macht typischerweise nur
wenige Prozent des HTML aus, eine HTML-Grenze verwirft also fast den
gesamten sichtbaren Inhalt.
"""

from __future__ import annotations

from psp_radar.collect.static import looks_like_payment_page
from psp_radar.core import load_registry, match_all
from psp_radar.core.models import SignalType, Stage
from psp_radar.core.observation import Observation, strip_tags


def kunstliche_shopseite(vorlauf_kb: int, satz: str) -> str:
    """Baut eine Seite, deren Text erst weit hinten beginnt.

    Genau die Bauform, an der die alte Fassung scheiterte: viel Skript- und
    Stilmasse vorne, der interessante Satz dahinter.
    """
    fuellung = "<script>var x = '" + ("a" * 900) + "';</script>\n"
    kopf = fuellung * (vorlauf_kb * 1000 // len(fuellung) + 1)
    return f"<html><head><style>{'b' * 50_000}</style></head><body>{kopf}<main><h1>Zahlungsarten</h1><p>{satz}</p></main></body></html>"


class TestStripTags:
    def test_langer_vorlauf_verdeckt_den_text_nicht(self) -> None:
        """Der Kern der Regression."""
        satz = "Die Abwicklung des Zahlungsprozesses erfolgt über Payolution/Unzer."
        html = kunstliche_shopseite(vorlauf_kb=600, satz=satz)

        assert len(html) > 600_000, "Testseite muss gross genug sein"
        text = strip_tags(html)

        assert "Payolution/Unzer" in text, (
            "Der Satz liegt hinter 600 KB Skriptmasse. Wird das HTML vor dem "
            "Entstrippen abgeschnitten, verschwindet er — genau der Fehler, "
            "der bergfreunde.de stumm machte."
        )
        assert "Zahlungsarten" in text

    def test_skripte_und_stile_landen_nicht_im_text(self) -> None:
        html = "<div>Sichtbar<script>geheim_var=1</script><style>.x{color:red}</style>Auch sichtbar</div>"
        text = strip_tags(html)
        assert "Sichtbar" in text and "Auch sichtbar" in text
        assert "geheim_var" not in text
        assert "color:red" not in text

    def test_kommentare_werden_entfernt(self) -> None:
        text = strip_tags("<p>Anfang<!-- interner Hinweis: Adyen -->Ende</p>")
        assert "Anfang" in text and "Ende" in text
        assert "Adyen" not in text, "Kommentare dürfen keine Treffer erzeugen"

    def test_entitaeten_werden_aufgeloest(self) -> None:
        """Sonst zerfällt 'Payolution&nbsp;/&nbsp;Unzer' und trifft nicht."""
        text = strip_tags("<p>Dienstleister Payolution&nbsp;/&nbsp;Unzer&#46;</p>")
        assert "Payolution" in text and "Unzer" in text

    def test_grenze_wirkt_am_text_nicht_am_html(self) -> None:
        """Ein kurzer Text in riesigem HTML muss vollständig ankommen."""
        html = "<div>" + "<span></span>" * 60_000 + "<p>Zahlung über Unzer</p></div>"
        assert len(html) > 700_000
        assert "Unzer" in strip_tags(html)

    def test_leeres_html_bricht_nicht(self) -> None:
        assert strip_tags("") == ""
        assert strip_tags("<html></html>") == ""


class TestZahlungsseitenErkennung:
    def test_pfad_und_text_muessen_beide_passen(self) -> None:
        """Zwei Bedingungen, damit eine 200er-Fehlerseite nicht durchgeht.

        Manche Shops liefern für unbekannte Pfade die Startseite mit Status
        200. Ohne Textprüfung wäre die dann eine "Zahlungsseite" — und ein
        dort zufällig erwähnter Anbieter bekäme das hohe Gewicht, das nur
        echten Aussagen zusteht.
        """
        assert looks_like_payment_page(
            "https://shop.de/lieferung-und-zahlung/",
            "Unsere Zahlungsmittel im Überblick: Rechnung, Kreditkarte",
        )
        # Pfad passt, Text nicht — vermutlich Startseite unter falschem Pfad
        assert not looks_like_payment_page(
            "https://shop.de/zahlungsarten/", "Willkommen in unserem Shop. Neuheiten."
        )
        # Text passt, Pfad nicht — etwa ein Blogartikel
        assert not looks_like_payment_page(
            "https://shop.de/blog/artikel/", "Welche Zahlungsart ist die beste?"
        )

    def test_bekannte_pfadvarianten_werden_erkannt(self) -> None:
        text = "Zahlungsarten im Überblick"
        for pfad in (
            "/lieferung-und-zahlung/",
            "/versand-und-zahlung/",
            "/zahlungsmittel/",
            "/zahlungsmethoden/",
            "/bezahlung/",
            "/payment-methods/",
            "/shipping-and-payment/",
        ):
            assert looks_like_payment_page(f"https://shop.de{pfad}", text), pfad


class TestPaymentPageTextSignal:
    def _obs(self, text: str, *, zahlungsseite: bool) -> Observation:
        return Observation(
            stage=Stage.STATIC,
            source_url="https://shop.de/lieferung-und-zahlung/",
            dom_text=text,
            is_payment_page=zahlungsseite,
        )

    def test_anbietername_auf_zahlungsseite_wird_stark_gewertet(self) -> None:
        satz = (
            "Zahle bequem auf Rechnung. Die Abwicklung des Zahlungsprozesses "
            "erfolgt über den Dienstleister Payolution/Unzer."
        )
        evidence = match_all(load_registry(), [self._obs(satz, zahlungsseite=True)])

        assert "unzer" in evidence
        beste = max(evidence["unzer"], key=lambda e: e.weight)
        assert beste.signal_type == SignalType.PAYMENT_PAGE_TEXT
        assert beste.weight >= 70, "Eine Aussage des Händlers ist mehr als ein Indiz"

    def test_derselbe_satz_auf_normaler_seite_wiegt_kaum(self) -> None:
        """Der Unterschied, der das hohe Gewicht überhaupt rechtfertigt."""
        satz = "Wir haben Payolution/Unzer in einem Blogartikel erwähnt."
        evidence = match_all(load_registry(), [self._obs(satz, zahlungsseite=False)])

        if "unzer" in evidence:
            beste = max(evidence["unzer"], key=lambda e: e.weight)
            assert beste.signal_type != SignalType.PAYMENT_PAGE_TEXT
            assert beste.weight <= 25, "Ausserhalb der Zahlungsseite nur schwaches Indiz"

    def test_blogartikel_ueber_stripe_erzeugt_keinen_sicheren_treffer(self) -> None:
        """Regressionsschutz gegen zu gierige Textsignale."""
        from psp_radar.eval.golden import evaluate_observations

        obs = Observation(
            stage=Stage.STATIC,
            source_url="https://shop.de/blog/zahlungsanbieter-vergleich/",
            dom_text="Ein Vergleich von Stripe, Adyen und Mollie für Onlineshops.",
            is_payment_page=False,
        )
        ergebnis = evaluate_observations([obs])
        assert ergebnis.primary_psp is None, "Ein Blogartikel darf keinen PSP ergeben"

    def test_wortgrenzen_verhindern_teiltreffer(self) -> None:
        """Ohne \\b würde 'Payoneer' als 'Payone' gelten."""
        evidence = match_all(
            load_registry(),
            [self._obs("Wir nutzen Payoneer für Auszahlungen an Partner.", zahlungsseite=True)],
        )
        assert "payone" not in evidence, "Payoneer ist nicht PAYONE"
