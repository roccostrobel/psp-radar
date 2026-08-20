"""Datenmodelle für den PSP-Detector.

Zentrale Idee: Die Pipeline-Stufen sammeln ausschliesslich *Evidenz*.
Sie fällen keine Urteile. Erst die Fusion (Stufe 4) verdichtet Evidenz zu
Detections. Dadurch bleibt jede Aussage des Tools rückverfolgbar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator


def _now() -> datetime:
    return datetime.now(UTC)


class Stage(StrEnum):
    """Pipeline-Stufe, in der eine Evidenz gefunden wurde."""

    NORMALIZE = "normalize"
    STATIC = "static"
    RENDER = "render"
    CHECKOUT = "checkout"


class SignalType(StrEnum):
    """Art eines Erkennungssignals.

    Die Reihenfolge spiegelt grob die Aussagekraft wider: Ein Live-Key im
    Quelltext oder ein Request an eine PSP-API ist deutlich belastbarer als
    ein Logo im Footer.
    """

    #: Request an einen Host (exakt oder Subdomain-Suffix)
    NETWORK_HOST = "network_host"
    #: Regex gegen die vollständige Request-URL
    NETWORK_URL_REGEX = "network_url_regex"
    #: Regex gegen den HTML-Quelltext
    HTML_REGEX = "html_regex"
    #: <script src="...">
    SCRIPT_SRC = "script_src"
    #: <iframe src="...">
    IFRAME_SRC = "iframe_src"
    #: Domain in der Content-Security-Policy (connect-src / frame-src / script-src)
    CSP_DOMAIN = "csp_domain"
    #: Cookie-Name (Regex)
    COOKIE = "cookie"
    #: HTTP-Response-Header, Format "name:regex"
    HEADER = "header"
    #: Sichtbarer Text im DOM (schwaches Signal, nur zur Stützung)
    DOM_TEXT = "dom_text"
    #: Anbietername auf einer **Zahlungsinformationsseite**.
    #:
    #: Der wichtigste Signaltyp für den DACH-Raum, und ein deutlich anderer
    #: Fall als DOM_TEXT. Auf einer Seite "Lieferung und Zahlung" oder
    #: "Zahlungsarten" ist ein genannter Anbieter keine Zufallserwähnung,
    #: sondern eine Aussage des Händlers über seine eigene Abwicklung —
    #: häufig sogar eine, zu der er rechtlich verpflichtet ist.
    #:
    #: Belegt an bergfreunde.de: "Der Zahlungsprozess wird über unseren
    #: Dienstleister Payolution/Unzer abgewickelt." Diese Seite kostet zwei
    #: Sekunden und beantwortet die Frage, für die sonst eine dreiminütige
    #: Checkout-Simulation nötig wäre.
    PAYMENT_PAGE_TEXT = "payment_page_text"
    #: Erreichbarer Pfad, z.B. /products.json
    WELLKNOWN = "wellknown"
    #: JS-Variable oder globales Objekt im gerenderten Kontext
    JS_GLOBAL = "js_global"


#: Signaltypen, deren `pattern` als regulärer Ausdruck ausgewertet wird.
#: Alle übrigen werden als Literal oder Hostname behandelt — ein `*.stripe.com`
#: ist eben kein Regex und darf auch nicht als solcher geprüft werden.
REGEX_SIGNAL_TYPES: frozenset[SignalType] = frozenset(
    {
        SignalType.NETWORK_URL_REGEX,
        SignalType.HTML_REGEX,
        SignalType.SCRIPT_SRC,
        SignalType.IFRAME_SRC,
        SignalType.COOKIE,
        SignalType.HEADER,
        SignalType.DOM_TEXT,
        SignalType.PAYMENT_PAGE_TEXT,
    }
)


class Role(StrEnum):
    """Rolle eines erkannten Anbieters.

    Diese Unterscheidung ist der wichtigste Teil des Modells. Ohne sie wirft
    man PayPal-Buttons und echte Acquirer in denselben Topf und erhält
    hübsche, aber wertlose Ergebnisse.
    """

    #: Echter Zahlungsabwickler / Acquirer (Stripe, Adyen, Unzer, ...)
    GATEWAY = "gateway"
    #: Orchestrierungsschicht über mehreren Gateways (Primer, Spreedly, ...)
    ORCHESTRATOR = "orchestrator"
    #: Wallet (Apple Pay, Google Pay, Amazon Pay, PayPal-Wallet)
    WALLET = "wallet"
    #: Zahlungsart / BNPL (Klarna, Ratepay, Rechnungskauf, SEPA)
    METHOD = "method"
    #: Shop-System (Shopify, Shopware, WooCommerce, ...)
    PLATFORM = "platform"
    #: Fraud-/Risk-Anbieter — Indiz für ein Enterprise-Setup
    FRAUD = "fraud"


class Confidence(StrEnum):
    """Sprachliche Einordnung des Zahlenwerts, damit Reports lesbar bleiben."""

    CERTAIN = "sicher"  # >= 90
    LIKELY = "wahrscheinlich"  # 70-89
    POSSIBLE = "moeglich"  # 45-69
    WEAK = "schwach"  # < 45

    @classmethod
    def from_score(cls, score: int) -> Confidence:
        if score >= 90:
            return cls.CERTAIN
        if score >= 70:
            return cls.LIKELY
        if score >= 45:
            return cls.POSSIBLE
        return cls.WEAK


# --------------------------------------------------------------------------
# Signatur-Datenbank (aus YAML geladen)
# --------------------------------------------------------------------------


class Signal(BaseModel):
    """Ein einzelnes Erkennungsmerkmal innerhalb einer Signatur."""

    type: SignalType
    pattern: str
    weight: int = Field(ge=1, le=100)
    #: Nur in diesen Stufen auswerten. None = in allen.
    stages: list[Stage] | None = None
    #: Freitext, warum dieses Signal aussagekräftig ist
    note: str | None = None

    model_config = {"frozen": True}


class Signature(BaseModel):
    """Ein erkennbarer Anbieter mit allen zugehörigen Signalen."""

    id: str
    name: str
    role: Role
    signals: list[Signal] = Field(min_length=1)

    #: Technischer Unterbau. Shopify Payments läuft z.B. auf Stripe.
    underlying: str | None = None
    #: Signatur greift nur, wenn diese Plattform erkannt wurde.
    requires_platform: str | None = None
    #: Andere Schreibweisen/Markennamen (z.B. Heidelpay -> Unzer)
    aliases: list[str] = Field(default_factory=list)
    #: Schwerpunktmärkte, rein informativ
    regions: list[str] = Field(default_factory=list)
    homepage: str | None = None
    #: Wenn gesetzt, verdrängt diese Signatur die genannten IDs bei Konflikten.
    #: Beispiel: shopify_payments unterdrückt eine generische stripe-Meldung.
    supersedes: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError(f"Signatur-ID muss ein Slug aus [a-z0-9_] sein, war: {v!r}")
        return v


# --------------------------------------------------------------------------
# Ergebnisse
# --------------------------------------------------------------------------


class Evidence(BaseModel):
    """Ein konkreter Fund. Jede Aussage des Tools lässt sich hierauf zurückführen."""

    signature_id: str
    signal_type: SignalType
    pattern: str
    #: Was tatsächlich gefunden wurde (URL, Cookie-Name, Regex-Treffer, ...)
    matched_value: str
    weight: int
    stage: Stage
    #: Auf welcher Seite der Fund passierte
    source_url: str | None = None
    seen_at: datetime = Field(default_factory=_now)

    def dedup_key(self) -> tuple[str, str, str]:
        """Identität für die Entdopplung.

        Ein und dasselbe Signal darf die Confidence nicht mehrfach anheben,
        nur weil ein Skript auf zehn Seiten eingebunden ist.
        """
        return (self.signature_id, str(self.signal_type), self.pattern)


class Detection(BaseModel):
    """Ein verdichteter Fund: Anbieter plus Confidence plus Belege."""

    id: str
    name: str
    role: Role
    confidence: int = Field(ge=0, le=100)
    #: Signatur-ID des technischen Unterbaus (z.B. "stripe")
    underlying: str | None = None
    #: Anzeigename dazu (z.B. "Stripe") — wird in der Fusion aufgelöst
    underlying_name: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)

    # computed_field statt @property: Nur so landen die Werte auch im JSON.
    # Ohne das fehlt der Oberfläche die Einstufung, und die farbige
    # Kennzeichnung bleibt stumm — ein Fehler, der beim Lesen des Codes
    # nicht auffällt, weil in Python alles korrekt funktioniert.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence_label(self) -> Confidence:
        return Confidence.from_score(self.confidence)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_count(self) -> int:
        return len(self.evidence)


class ScanWarning(BaseModel):
    """Etwas ist schiefgelaufen oder ein Ergebnis ist eingeschränkt gültig."""

    code: str
    message: str
    stage: Stage | None = None


class ScanResult(BaseModel):
    """Das Gesamtergebnis für eine Shop-URL."""

    url: str
    final_url: str | None = None
    final_domain: str | None = None

    platform: Detection | None = None
    psps: list[Detection] = Field(default_factory=list)
    payment_methods: list[Detection] = Field(default_factory=list)
    wallets: list[Detection] = Field(default_factory=list)
    fraud_tools: list[Detection] = Field(default_factory=list)

    #: Wurde eine Checkout-Seite erreicht? Stammt aus dem `CheckoutOutcome`,
    #: nicht daraus, ob eine Observation die Stufe CHECKOUT trägt.
    checkout_reached: bool = False
    #: Wurde die **Zahlungsauswahl** erreicht — der Schritt, in dem der
    #: Abwickler lädt? Das ist die schärfere und ehrlichere Aussage.
    #:
    #: Die Trennung ist nötig, weil beides auseinanderfällt: Bei snocks.com
    #: wurde die Checkout-Seite erreicht und Shopify Payments zu 98 %
    #: erkannt, die Zahlungsauswahl selbst aber nicht. Ein einziges
    #: "Checkout erreicht ✓" neben der Warnung "Zahlungsauswahl nicht
    #: erreicht" ist verwirrend, und Verwirrung über den erreichten Stand
    #: ist genau die Fehlerart, die Regel 5 verhindern soll.
    payment_selection_reached: bool = False
    #: Welche Stufen tatsächlich gelaufen sind
    stages_run: list[Stage] = Field(default_factory=list)

    overall_confidence: int = 0
    warnings: list[ScanWarning] = Field(default_factory=list)
    #: In welcher Trichterstufe das Ergebnis entstand: "statisch",
    #: "gerendert" oder "checkout". Gehört sichtbar in den Report — ein
    #: Treffer aus der statischen Prüfung ist etwas anderes als einer aus
    #: dem echten Checkout, auch wenn beide dieselbe Zahl tragen.
    tier: str = "statisch"
    duration_s: float = 0.0
    scanned_at: datetime = Field(default_factory=_now)
    #: Version der Signatur-DB, mit der gescannt wurde
    signature_version: str | None = None

    @property
    def primary_psp(self) -> Detection | None:
        """Der wahrscheinlichste echte Zahlungsabwickler, oder None."""
        gateways = [d for d in self.psps if d.role in (Role.GATEWAY, Role.ORCHESTRATOR)]
        return max(gateways, key=lambda d: d.confidence, default=None)

    # ------------------------------------------------------------------
    # Belegart des Acquirers
    #
    # Die Prozentzahl allein sagt zu wenig. Gemessen über 15 DACH-Shops ist
    # der Acquirer ohne Checkout nur bei etwa einem Viertel bestimmbar
    # (docs/BEFUNDE.md) — die Frage ist also nicht nur "wie sicher", sondern
    # vor allem "woher". Ein im Checkout beobachteter Request an die
    # Zahlungs-API ist etwas anderes als ein Satz auf der Seite "Lieferung
    # und Zahlung", und beides ist etwas anderes als ein Host, der auf der
    # Startseite auftaucht.
    #
    # Als computed_field, nicht als property: sonst fehlt es im JSON und die
    # Oberfläche kann es nicht anzeigen.
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def acquirer_source(self) -> str:
        """Woher die Aussage über den Zahlungsabwickler stammt.

        - `beobachtet` — im Checkout tatsächlich geladen. Der stärkste Beleg.
        - `angegeben` — der Händler nennt den Dienstleister selbst auf seiner
          Zahlungsseite. Eine Aussage, nicht eine Beobachtung, aber eine, zu
          der er oft verpflichtet ist.
        - `vermutet` — nur indirekte Spuren: Hosts, Assets, Verbindungshinweise.
        - `keine` — nichts gefunden.
        """
        psp = self.primary_psp
        if psp is None:
            return "keine"
        if any(e.stage == Stage.CHECKOUT for e in psp.evidence):
            return "beobachtet"
        if any(e.signal_type == SignalType.PAYMENT_PAGE_TEXT for e in psp.evidence):
            return "angegeben"
        return "vermutet"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def acquirer_note(self) -> str:
        """Ein Satz dazu, was das Ergebnis wert ist — oder was fehlt.

        Bei `keine` ist die Unterscheidung wichtig, die im Vorgänger fehlte:
        Ein nicht erreichter Checkout ist ein Adapterproblem, ein erreichter
        Checkout ohne Treffer eine fehlende Signatur. Wer das verwechselt,
        erweitert die Signaturdatenbank, während der Adapter kaputt ist.
        """
        quelle = self.acquirer_source
        if quelle == "beobachtet":
            return "Im Checkout beobachtet — der belastbarste Beleg."
        if quelle == "angegeben":
            return "Vom Händler auf seiner Zahlungsseite genannt, nicht im Checkout beobachtet."
        if quelle == "vermutet":
            return (
                "Nur indirekte Spuren. Ohne Checkout-Beobachtung bleibt offen, "
                "wer die Kartenzahlung tatsächlich abwickelt."
            )

        codes = {w.code for w in self.warnings}
        if self.checkout_reached:
            return (
                "Checkout erreicht, aber kein bekannter Anbieter erkannt — "
                "wahrscheinlich fehlt die Signatur. Netzwerk-Hosts manuell sichten."
            )
        if "checkout_cart_empty" in codes or "checkout_add_to_cart_failed" in codes:
            return (
                "Der Artikel landete nicht im Warenkorb, der Checkout wurde nie erreicht. "
                "Ursache sind die Selektoren des Adapters, nicht fehlende Signaturen."
            )
        if "no_payment_page" in codes:
            return (
                "Kein Checkout und keine Zahlungsseite gefunden. "
                "Damit gibt es keine Quelle, aus der der Abwickler hervorgehen könnte."
            )
        return (
            "Nicht ermittelt. Der Abwickler lädt bei vielen Shops erst nach der "
            "Zahlungsauswahl — dort endet die Simulation aus gutem Grund."
        )

    def summary_line(self) -> str:
        """Einzeiler für Terminal und CSV."""
        psp = self.primary_psp
        platform = self.platform.name if self.platform else "unbekannt"
        if psp is None:
            return f"{self.final_domain or self.url}: PSP unbekannt (Shop-System: {platform})"
        return (
            f"{self.final_domain or self.url}: {psp.name} "
            f"({psp.confidence}%, {psp.confidence_label}) · Shop-System: {platform}"
        )
