"""Tests der Confidence-Berechnung.

Kernanliegen: Das Tool darf sich nicht sicherer geben, als es ist.
Viele schwache Signale dürfen nie zu einer hohen Confidence führen.
"""

from __future__ import annotations

from datetime import UTC, datetime

from psp_radar.core.models import Evidence, SignalType, Stage
from psp_radar.core.scoring import checkout_bonus, combine_weights, dedupe, score_evidence


def ev(
    weight: int,
    *,
    sig: str = "stripe",
    pattern: str = "p",
    stage: Stage = Stage.STATIC,
    signal: SignalType = SignalType.NETWORK_HOST,
) -> Evidence:
    return Evidence(
        signature_id=sig,
        signal_type=signal,
        pattern=pattern,
        matched_value="x",
        weight=weight,
        stage=stage,
        seen_at=datetime.now(UTC),
    )


class TestCombineWeights:
    def test_keine_signale_ergibt_null(self) -> None:
        assert combine_weights([]) == 0

    def test_einzelnes_hartes_signal_bleibt_erhalten(self) -> None:
        """Ein Live-Key im Quelltext reicht allein — er wird nicht abgeschwächt."""
        assert combine_weights([99]) == 99

    def test_zwei_starke_signale_naehern_sich_hundert(self) -> None:
        assert combine_weights([95, 88]) >= 98

    def test_ueberschreitet_niemals_hundert(self) -> None:
        assert combine_weights([99, 99, 99, 99, 99, 99]) <= 100

    def test_viele_schwache_signale_erzeugen_keine_scheinsicherheit(self) -> None:
        """Der entscheidende Test.

        Fünf Signale à 20 ergäben bei Addition 100 — also scheinbare
        Gewissheit aus lauter schwachen Indizien. Genau das darf nicht
        passieren. Das Ergebnis muss deutlich unter 'sicher' bleiben.
        """
        score = combine_weights([20, 20, 20, 20, 20])
        assert score < 70, f"Schwache Signale ergeben {score}% — zu selbstsicher"
        assert score > 30, "Mehrere Indizien sollten sich trotzdem stützen"

    def test_reihenfolge_ist_egal(self) -> None:
        assert combine_weights([20, 90, 50]) == combine_weights([50, 20, 90])

    def test_daempfung_wirkt(self) -> None:
        """Jedes weitere Signal trägt weniger bei als das vorherige."""
        eins = combine_weights([50])
        zwei = combine_weights([50, 50])
        drei = combine_weights([50, 50, 50])
        assert eins < zwei < drei
        assert (zwei - eins) > (drei - zwei)

    def test_nullgewichte_werden_ignoriert(self) -> None:
        assert combine_weights([0, 0, 80]) == combine_weights([80])


class TestDedupe:
    def test_identisches_signal_zaehlt_nur_einmal(self) -> None:
        """Ein Skript auf zehn Seiten ist ein Indiz, nicht zehn."""
        evidence = [ev(88, pattern="js.stripe.com") for _ in range(10)]
        assert len(dedupe(evidence)) == 1

    def test_verschiedene_signale_bleiben_erhalten(self) -> None:
        evidence = [ev(88, pattern="a"), ev(95, pattern="b"), ev(70, pattern="c")]
        assert len(dedupe(evidence)) == 3

    def test_checkout_stufe_gewinnt_gegen_static(self) -> None:
        """Der Fund im Checkout ist aussagekräftiger und soll erhalten bleiben."""
        evidence = [
            ev(88, pattern="js.stripe.com", stage=Stage.STATIC),
            ev(88, pattern="js.stripe.com", stage=Stage.CHECKOUT),
        ]
        result = dedupe(evidence)
        assert len(result) == 1
        assert result[0].stage == Stage.CHECKOUT

    def test_zehnfaches_signal_hebt_confidence_nicht(self) -> None:
        einmal, _ = score_evidence([ev(60, pattern="x")])
        zehnmal, _ = score_evidence([ev(60, pattern="x") for _ in range(10)])
        assert einmal == zehnmal


class TestCheckoutBonus:
    def test_ohne_checkout_keine_aufwertung(self) -> None:
        assert checkout_bonus(70, reached_checkout=False) == 70

    def test_mit_checkout_wird_aufgewertet(self) -> None:
        assert checkout_bonus(70, reached_checkout=True) > 70

    def test_bonus_sprengt_nie_die_grenze(self) -> None:
        assert checkout_bonus(99, reached_checkout=True) <= 100
