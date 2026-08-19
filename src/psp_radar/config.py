"""Konfiguration eines Scans.

Defaults sind so gewählt, dass ein Lauf ohne Argumente die höchste
Trefferquote liefert — Tiefe vor Tempo. Wer viele Shops scannt, dreht
bewusst herunter, nicht andersherum.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: Ehrlicher, identifizierbarer User-Agent. Wer scannt, sollte ansprechbar sein.
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
    "psp-detector/0.1 (+https://github.com/roccostrobel/psp-detector)"
)


class ScanConfig(BaseModel):
    """Alle Stellschrauben eines Scans."""

    # --- Tiefe ---
    enable_render: bool = True
    enable_checkout: bool = True

    #: Trichterbetrieb — teurere Stufen überspringen, wenn das Ergebnis
    #: bereits eindeutig scheint.
    #:
    #: **Standardmässig AUS.** Das ist eine bewusste Umkehr gegenüber dem
    #: ersten Entwurf. Der Trichter ist verlockend, weil er Zeit spart, aber
    #: er verlässt sich auf Schwellwerte, die noch nicht gegen ein
    #: belastbares Golden-Set kalibriert sind. Solange das so ist, würde
    #: jeder frühe Ausstieg auf Verdacht erfolgen — und ein schnelles
    #: falsches Ergebnis ist schlechter als ein langsames richtiges.
    #:
    #: Wer ihn einschaltet, bekommt Tempo gegen ein kalkuliertes Risiko.
    #: Wieder auf Standard zu stellen ist erst zu verantworten, wenn
    #: `psp-radar eval --calibrate` belegt, was er an Recall kostet.
    auto_depth: bool = False

    # --- Schwellwerte des Trichters (nur wirksam bei auto_depth) ---
    #
    # Der einzige Ort im Projekt, an dem Tempo gegen Genauigkeit getauscht
    # wird. Beide Werte liegen bewusst hoch: Sie greifen praktisch nur bei
    # Beweisen — Live-Key im Quelltext, PSP-Domain in der CSP, Anbietername
    # auf der Zahlungsinformationsseite —, nicht bei Indizien.
    skip_render_threshold: int = 97
    skip_checkout_threshold: int = 95

    # --- Zeitbudget (Sekunden) ---
    static_timeout: float = 20.0
    page_timeout: float = 45.0
    checkout_timeout: float = 90.0
    total_timeout: float = 240.0

    # --- Verhalten gegenüber dem Shop ---
    respect_robots: bool = True
    #: Wartezeit zwischen zwei Requests an dieselbe Domain
    delay_between_requests: float = 1.0
    max_retries: int = 2
    user_agent: str = DEFAULT_UA
    #: Sprache/Region, beeinflusst welche Zahlungsarten ein Shop anzeigt
    accept_language: str = "de-DE,de;q=0.9,en;q=0.6"
    locale: str = "de-DE"

    # --- Browser ---
    headless: bool = True
    viewport_width: int = 1440
    viewport_height: int = 900
    #: Bilder/Fonts blockieren. Spart viel Zeit, ändert nichts an den
    #: relevanten Signalen — die stecken in XHR/Fetch und Skripten.
    block_media: bool = True

    # --- Checkout-Simulation ---
    #: Wie viele Produkte höchstens probiert werden, wenn eines scheitert
    max_product_attempts: int = 3
    #: Dummy-Daten für den Gast-Checkout. Bewusst erkennbar synthetisch.
    dummy_email: str = "psp-detector-test@example.com"
    dummy_first_name: str = "Test"
    dummy_last_name: str = "Testerson"
    dummy_street: str = "Teststrasse 1"
    dummy_zip: str = "10115"
    dummy_city: str = "Berlin"
    dummy_country: str = "DE"
    dummy_phone: str = "+49 30 000000"

    # --- Batch ---
    concurrency: int = Field(default=4, ge=1, le=16)
    #: Gleichzeitige HTTP-Abrufe **innerhalb eines Shops** in Stufe 1.
    #: Klein gehalten: Es geht darum, 30 Pfade nicht sequenziell abzuklappern,
    #: nicht darum, einen Shop mit Anfragen zu überziehen.
    static_concurrency: int = Field(default=4, ge=1, le=8)


#: Beschriftungen, die auf einen kaufauslösenden Button hindeuten. Elemente
#: mit einem dieser Muster werden NIEMALS angeklickt.
#:
#: Die Liste ist bewusst grosszügig. Ein fälschlich blockierter Button kostet
#: ein Signal; ein fälschlich geklickter kostet eine echte Bestellung bei
#: einem echten Händler. Die Asymmetrie ist eindeutig.
#:
#: Der deutsche Rechtsrahmen hilft hier: § 312j Abs. 3 BGB schreibt für
#: Verbraucherverträge eine eindeutige Beschriftung vor. Deshalb enthält
#: praktisch jeder deutsche Kaufbutton "pflichtig" — "zahlungspflichtig
#: bestellen", "kostenpflichtig bestellen", "zahlungspflichtig buchen".
#: Ein einzelnes Muster deckt damit die gesamte Familie ab.
FORBIDDEN_SUBMIT_PATTERNS = (
    r"pflichtig",
    r"kaufen",
    r"jetzt\s*bestellen",
    r"verbindlich\s*bestell",
    r"bestellung\s*(?:abschlie|absenden|abschicken|aufgeben)",
    r"zahlung\s*(?:jetzt\s*)?(?:ausf|abschlie|best)",
    r"order\s*now",
    r"place\s*(?:your\s*)?order",
    r"complete\s*(?:your\s*)?(?:order|purchase)",
    r"submit\s*order",
    r"pay\s*now",
    r"confirm\s*(?:and|und|&)?\s*pay",
    r"finish\s*(?:and|&)?\s*pay",
    r"buy\s*now",
    r"purchase\s*now",
)
