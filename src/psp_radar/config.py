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
#:
#: **Diese Liste darf nur erweitert, nie gekürzt werden.**
FORBIDDEN_SUBMIT_PATTERNS = (
    r"pflichtig",
    r"kaufen",
    # "Kauf abschliessen" enthält kein "kaufen" — eigene Zeile nötig
    r"kauf\s*(?:abschlie|bestätig|bestatig|absenden|tätigen|taetigen)",
    r"jetzt\s*bestellen",
    r"verbindlich\s*bestell",
    r"bestellung\s*(?:abschlie|absenden|abschicken|aufgeben|bestätig|bestatig|bezahl)",
    r"bestellen\s*(?:und|&)\s*(?:be)?zahlen",
    r"zahlung\s*(?:jetzt\s*)?(?:ausf|abschlie|best|freigeb)",
    # "Jetzt zahlen" / "Jetzt bezahlen" — häufig auf der Zahlungsseite
    r"jetzt\s*(?:be)?zahlen",
    r"jetzt\s*(?:buchen|abschlie|beauftrag)",
    r"buchung\s*(?:abschlie|bestätig|bestatig)",
    # "Weiter und bezahlen", "Review and pay", "Confirm & pay"
    r"(?:and|und|&)\s*(?:pay|(?:be)?zahlen)\b",
    r"order\s*now",
    r"place\s*(?:your\s*)?order",
    r"complete\s*(?:your\s*)?(?:order|purchase|payment)",
    r"submit\s*(?:your\s*)?order",
    r"pay\s*now",
    r"confirm\s*(?:and|und|&)?\s*(?:pay|order|purchase)",
    r"finish\s*(?:and|&)?\s*pay",
    r"buy\s*now",
    r"purchase\s*now",
    r"checkout\s*(?:and|&)\s*pay",
    # Abos und Spenden lösen ebenfalls eine Zahlungspflicht aus
    r"abonnier",
    r"subscribe",
    r"spenden",
    r"donate",
    # Nicht-DACH-Kaufbuttons. Ausserhalb des Schwerpunkts, aber ein
    # Muster kostet nichts und ein Fehlklick kostet eine Bestellung.
    r"comprar",
    r"acheter",
    r"acquista",
    r"koop\s*nu",
    r"bestel\s*nu",
    r"köp\s*nu",
)

#: Beschriftungen, die **allein stehend** eine Bestellung auslösen können.
#:
#: Diese brauchen eine eigene Behandlung, weil sie als Teilwort harmlos sind.
#: "Als Gast bestellen" muss geklickt werden dürfen, ein Button, auf dem nur
#: "Bestellen" steht, nicht. Ein Substring-Verbot auf "bestellen" würde
#: entweder zu viel oder zu wenig blockieren — deshalb wird hier die
#: **vollständige Beschriftung** verglichen, nicht ein Vorkommen darin.
#:
#: Dass damit auch harmlose Weiter-Buttons wie ein blosses "Bestätigen"
#: blockiert werden, ist beabsichtigt. Es kostet bei manchen Shops ein
#: Signal. Die Alternative wäre, auf der letzten Seite vor dem Kaufbutton zu
#: raten, welches "Bestätigen" gemeint ist.
FORBIDDEN_STANDALONE_LABELS = (
    "bestellen",
    "bestellung",
    "kaufen",
    "kauf",
    "bezahlen",
    "zahlen",
    "abschicken",
    "absenden",
    "abschliessen",
    "abschließen",
    "bestätigen",
    "bestatigen",
    "order",
    "pay",
    "buy",
    "purchase",
    "submit",
    "confirm",
    "checkout & pay",
)

#: Formularfelder, in die **niemals** etwas eingetragen wird.
#:
#: Der Gast-Checkout wird mit erkennbar synthetischen Adressdaten befüllt,
#: damit die Zahlungsauswahl überhaupt erscheint. Zahlungsdaten gehören
#: ausdrücklich nicht dazu — auch keine Testkartennummern. Ein Feld gilt als
#: Zahlungsfeld, wenn `name`, `id`, `autocomplete`, `placeholder` oder
#: `aria-label` eines dieser Muster enthält.
#:
#: Geprüft wird beim Ausfüllen, nicht beim Zusammenstellen der Selektoren.
#: Der Grund: Selektorlisten wachsen, und `input[name*='address' i]` kann
#: auf einer ungewöhnlich gebauten Seite auch ein Feld der Kartenmaske
#: treffen. Die Sperre sitzt deshalb an der Stelle, die alle Wege passieren.
FORBIDDEN_FIELD_PATTERNS = (
    r"\bcc[-_]?(?:num|number|name|exp|csc|cvc|cvv)",
    r"card[-_]?(?:num|number|holder|name|expiry|exp|month|year)",
    r"kreditkarte",
    r"kartennummer",
    r"\bcvc\b",
    r"\bcvv\b",
    r"\bcsc\b",
    r"security[-_]?code",
    r"pr(?:ü|ue)fnummer",
    r"\biban\b",
    r"\bbic\b",
    r"kontonummer",
    r"bankleitzahl",
    r"account[-_]?number",
    r"routing[-_]?number",
    r"sort[-_]?code",
    r"expir(?:y|ation)",
    r"\bpassword\b",
    r"\bpasswort\b",
    r"\bpin\b",
    r"\bsepa\b",
    r"mandat",
)

#: URL-Bestandteile, die auf einen Bestellabschluss hindeuten. Es wird nie
#: dorthin navigiert — auch nicht per GET.
#:
#: Anlass: Die Adapter raten Checkout-Pfade (`/checkout/confirm`,
#: `/?cl=user`). Raten ist hier vertretbar, weil diese Seiten nur anzeigen.
#: Ein geratener Pfad wie `/checkout/finish` wäre es nicht. Ein sauber
#: gebauter Shop führt eine Bestellung nicht auf ein GET aus — aber sich
#: darauf zu verlassen, dass fremder Code sauber gebaut ist, ist keine
#: Sicherheitsmassnahme.
FORBIDDEN_URL_PATTERNS = (
    r"/checkout/finish",
    r"/checkout/(?:place|submit)",
    r"/order/(?:place|submit|finish|create|confirm)",
    r"/bestellung/(?:abschlie|absenden|bestaetig)",
    r"place[-_]?order",
    r"submit[-_]?order",
    r"confirm[-_]?order",
    r"complete[-_]?order",
    r"order[-_]?received",
    r"order[-_]?success",
    r"danke[-_]?f(?:ü|ue)r[-_]?(?:ihre|deine)[-_]?bestellung",
    r"thank[-_]?you[-_]?for[-_]?your[-_]?order",
    r"cl=order",
    r"cl=thankyou",
)
