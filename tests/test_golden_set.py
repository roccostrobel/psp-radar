"""Prüft das Golden-Set selbst, nicht die Erkennung.

Ein Golden-Set mit schlechten Einträgen ist schlimmer als keines: Es
kalibriert das Tool auf Vermutungen und lässt die Metrik gut aussehen,
während die Erkennung schlechter wird. Diese Tests sind der Türsteher.

Der wichtigste davon ist `test_kein_eintrag_ist_nur_tool_belegt`. Ein
Eintrag, dessen Beleg vom eigenen Tool stammt, misst nur, ob das Tool mit
sich selbst übereinstimmt — und genau dieser Fehler ist verführerisch,
weil er die Zahlen sofort verbessert.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

GOLDEN = Path(__file__).resolve().parent / "golden_set.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Belegarten, die als unabhängige Verifikation gelten
GUELTIGE_BELEGE = {"checkout_manual", "impressum", "csp_header", "presse"}

#: Zielgrösse laut docs/ACCEPTANCE.md M2
MINDESTANZAHL = 25


def eintraege() -> list[dict]:
    if not GOLDEN.exists():
        return []
    raw = yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or {}
    return list(raw.get("shops", []))


def verifizierte() -> list[dict]:
    return [e for e in eintraege() if e.get("verified_via") in GUELTIGE_BELEGE]


def test_golden_set_ist_lesbar() -> None:
    assert eintraege(), "golden_set.yaml enthält keine Einträge"


def test_jeder_eintrag_hat_die_pflichtfelder() -> None:
    fehlend: list[str] = []
    for entry in eintraege():
        for feld in ("url", "expected_psp", "verified_via"):
            if feld not in entry:
                fehlend.append(f"{entry.get('url', '?')}: {feld} fehlt")
    assert not fehlend, "\n  - ".join(["Pflichtfelder fehlen:", *fehlend])


def test_kein_eintrag_ist_nur_tool_belegt() -> None:
    """`tool_observed` zählt nicht als Verifikation.

    Solche Einträge sind als Zwischenstand erlaubt, dürfen aber nicht in
    die Metrik eingehen. Dieser Test macht sichtbar, wie viele noch offen
    sind, statt sie stillschweigend mitzuzählen.
    """
    offen = [
        e["url"]
        for e in eintraege()
        if e.get("verified_via") in ("", "tool_observed", None) or e.get("expected_psp") == "TODO"
    ]
    if offen:
        pytest.skip(
            f"{len(offen)} Eintrag/Einträge noch nicht unabhängig verifiziert: "
            + ", ".join(offen[:6])
        )


def test_belegarten_sind_gueltig() -> None:
    erlaubt = GUELTIGE_BELEGE | {"", "tool_observed"}
    ungueltig = [
        f"{e.get('url')}: {e.get('verified_via')!r}"
        for e in eintraege()
        if e.get("verified_via") not in erlaubt
    ]
    assert not ungueltig, "Unbekannte Belegart:\n  - " + "\n  - ".join(ungueltig)


def test_keine_doppelten_shops() -> None:
    urls = [e["url"].rstrip("/").removeprefix("https://").removeprefix("www.") for e in eintraege()]
    doppelt = {u for u in urls if urls.count(u) > 1}
    assert not doppelt, f"Doppelte Einträge: {doppelt}"


def test_psp_ids_existieren_in_der_signaturdatenbank() -> None:
    """Ein Tippfehler hier würde das Tool gegen einen nicht existierenden
    Anbieter messen und dauerhaft als Fehler gezählt werden."""
    from psp_radar.core import load_registry

    registry = load_registry()
    unbekannt: list[str] = []
    for entry in eintraege():
        for feld in ("expected_psp", "expected_platform"):
            wert = entry.get(feld)
            if wert and wert != "TODO" and registry.get(wert) is None:
                unbekannt.append(f"{entry['url']}: {feld}={wert!r}")

    assert not unbekannt, "Unbekannte Signatur-ID:\n  - " + "\n  - ".join(unbekannt)


# --- Kriterien aus docs/ACCEPTANCE.md M2, noch nicht erfüllt ---


def test_mindestanzahl_erreicht() -> None:
    anzahl = len(verifizierte())
    if anzahl < MINDESTANZAHL:
        pytest.skip(
            f"M2 noch offen: {anzahl} von {MINDESTANZAHL} unabhängig verifizierten Shops"
        )


def test_vielfalt() -> None:
    """Vielfalt schlägt Menge.

    Dreissig Shopify-Shops sagen weniger aus als zehn über verschiedene
    Systeme hinweg — das Tool würde auf einen Sonderfall kalibriert.
    """
    eintr = verifizierte()
    if len(eintr) < MINDESTANZAHL:
        pytest.skip("Erst sinnvoll, wenn das Set gefüllt ist")

    systeme = {e.get("expected_platform") for e in eintr if e.get("expected_platform")}
    psps = {e["expected_psp"] for e in eintr}

    assert len(systeme) >= 5, f"Nur {len(systeme)} Shop-System(e) vertreten: {systeme}"
    assert len(psps) >= 6, f"Nur {len(psps)} PSP(s) vertreten: {psps}"


def test_fixtures_vollstaendig() -> None:
    """Ohne Fixture läuft der Eintrag nicht in der Offline-Auswertung mit."""
    eintr = verifizierte()
    if not eintr:
        pytest.skip("Keine verifizierten Einträge")

    fehlend: list[str] = []
    for entry in eintr:
        name = entry.get("fixture") or (
            entry["url"].removeprefix("https://").removeprefix("http://").rstrip("/")
            .replace(".", "_").replace("/", "_").removeprefix("www_")
        )
        if not (FIXTURES / f"{name}.json").exists():
            fehlend.append(f"{entry['url']} → {name}.json")

    if fehlend:
        pytest.skip(f"{len(fehlend)} Fixture(s) fehlen noch:\n  - " + "\n  - ".join(fehlend[:8]))
