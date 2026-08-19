"""Prüft, dass Frontend und API dieselbe Sprache sprechen.

Anlass ist ein echter Fehler: Beim Umbau von psp-detector auf psp-radar
wurde der Abfrage-Endpunkt von `/api/scan/{id}` zu `/api/job/{id}`
umbenannt. Die HTML-Vorlage wurde unverändert übernommen und fragte weiter
den alten Pfad ab.

Das Ergebnis war das unangenehmste mögliche Verhalten: Der Klick auf
"Analysieren" tat scheinbar **nichts**. Der Scan lief im Hintergrund
korrekt durch, der POST kam an, aber die 404-Antwort auf die Fortschritts-
abfrage landete stillschweigend im Nichts. Kein Fehler, keine Meldung,
keine Spur — nur ein Knopf, der nicht reagiert.

Ein Integrationstest über den echten Browser wäre der gründlichere Weg,
kostet aber Playwright und Minuten. Dieser Test kostet Millisekunden und
hätte den Fehler ebenso gefunden.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from psp_radar.api import build_app
from psp_radar.web import template


def registrierte_pfade() -> set[str]:
    app = build_app()
    return {getattr(route, "path", "") for route in app.routes}


def aufgerufene_pfade() -> set[str]:
    """Zieht alle fetch()-Ziele aus der HTML-Vorlage.

    Erfasst beide Schreibweisen: Zeichenkette in Anführungszeichen und
    Template-Literal mit eingesetzter Variable.
    """
    quelle = template._JS + template.INDEX_HTML
    treffer: set[str] = set()

    # fetch("/api/...") und fetch(`/api/...`)
    for match in re.finditer(r"""(?:fetch|holen)\(\s*[`'"](/api/[^`'"]*)[`'"]""", quelle):
        treffer.add(match.group(1))
    # location.href = '/api/...'
    for match in re.finditer(r"""location\.href\s*=\s*[`'"](/api/[^`'"]*)[`'"]""", quelle):
        treffer.add(match.group(1))

    return treffer


def normalisiere(pfad: str) -> str:
    """Ersetzt eingesetzte JS-Variablen durch FastAPI-Platzhalter.

    `/api/job/${jobId}` und `/api/job/{job_id}` sollen als derselbe Pfad
    gelten, damit der Vergleich funktioniert.
    """
    pfad = re.sub(r"\$\{[^}]+\}", "{x}", pfad)
    return re.sub(r"\{[^}]+\}", "{x}", pfad)


def test_frontend_ruft_nur_existierende_endpunkte_auf() -> None:
    vorhanden = {normalisiere(p) for p in registrierte_pfade()}
    gerufen = aufgerufene_pfade()

    assert gerufen, "Kein einziger API-Aufruf in der Vorlage gefunden — Test greift ins Leere"

    fehlend = sorted(p for p in gerufen if normalisiere(p) not in vorhanden)
    assert not fehlend, (
        "Das Frontend ruft Endpunkte auf, die es nicht gibt. Der Knopf würde "
        "scheinbar nichts tun:\n  - "
        + "\n  - ".join(fehlend)
        + "\n\nVorhanden sind:\n  - "
        + "\n  - ".join(sorted(vorhanden))
    )


def test_wichtige_endpunkte_existieren() -> None:
    vorhanden = registrierte_pfade()
    for pfad in ("/", "/api/scan", "/api/batch", "/api/job/{job_id}", "/api/health"):
        assert pfad in vorhanden, f"Endpunkt fehlt: {pfad}"


def test_seite_wird_ausgeliefert() -> None:
    client = TestClient(build_app())
    antwort = client.get("/")
    assert antwort.status_code == 200
    # Platzhalter müssen ersetzt sein, sonst steht Rohtext in der Seite
    assert "__CSS__" not in antwort.text
    assert "__JS__" not in antwort.text
    assert "{{SIGNATUREN}}" not in antwort.text
    assert "#fc1154" in antwort.text, "Markenfarbe fehlt"


def test_einzelscan_laesst_sich_starten_und_abfragen() -> None:
    """Der Weg, der vorher gebrochen war: starten, dann Fortschritt abfragen."""
    client = TestClient(build_app())

    gestartet = client.post("/api/scan", json={"url": "https://example.invalid", "mode": "statisch"})
    assert gestartet.status_code == 200
    job_id = gestartet.json()["id"]

    abfrage = client.get(f"/api/job/{job_id}")
    assert abfrage.status_code == 200, "Die Fortschrittsabfrage muss erreichbar sein"

    daten = abfrage.json()
    for feld in ("status", "stage", "progress", "elapsed", "kind"):
        assert feld in daten, f"Feld {feld} fehlt in der Antwort — Frontend erwartet es"


def test_listenscan_laesst_sich_starten() -> None:
    client = TestClient(build_app())
    antwort = client.post(
        "/api/batch",
        json={"urls": ["https://example.invalid", "https://example.invalid"], "mode": "statisch"},
    )
    assert antwort.status_code == 200
    # Doppelte Eingaben werden zusammengefasst
    assert antwort.json()["anzahl"] == 1


def test_unbekannter_auftrag_gibt_klaren_fehler() -> None:
    """404 ist in Ordnung — stilles Nichts nicht."""
    client = TestClient(build_app())
    antwort = client.get("/api/job/gibtesnicht")
    assert antwort.status_code == 404
    assert "detail" in antwort.json()


def test_csv_export_ist_erreichbar() -> None:
    client = TestClient(build_app())
    job_id = client.post(
        "/api/batch", json={"urls": ["https://example.invalid"], "mode": "statisch"}
    ).json()["id"]

    antwort = client.get(f"/api/job/{job_id}/csv")
    assert antwort.status_code == 200
    assert "url" in antwort.text.split("\n")[0], "Kopfzeile der CSV fehlt"


@pytest.mark.parametrize("modus", ["trichter", "voll", "schnell", "statisch"])
def test_alle_in_der_oberflaeche_angebotenen_modi_werden_akzeptiert(modus: str) -> None:
    """Die Radio-Buttons dürfen keine Werte anbieten, die die API ablehnt."""
    client = TestClient(build_app())
    antwort = client.post("/api/scan", json={"url": "https://example.invalid", "mode": modus})
    assert antwort.status_code == 200, f"Modus {modus!r} wird von der API abgelehnt"


def test_oberflaeche_bietet_nur_gueltige_modi_an() -> None:
    """Gegenrichtung: kein Radio-Button ohne Rückhalt in der API."""
    angeboten = set(re.findall(r"""name=["']mode["']\s+value=["']([^"']+)["']""", template.INDEX_HTML))
    assert angeboten, "Keine Modus-Auswahl in der Vorlage gefunden"

    from psp_radar.api.app import ScanRequest

    erlaubt = set(ScanRequest.model_fields["mode"].annotation.__args__)  # type: ignore[union-attr]
    assert angeboten <= erlaubt, f"Oberfläche bietet unbekannte Modi an: {angeboten - erlaubt}"
