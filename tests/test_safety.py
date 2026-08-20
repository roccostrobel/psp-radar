"""Sicherheitstests — der wichtigste Testfile im Projekt.

Das Tool klickt sich durch fremde Checkouts. Wenn hier etwas durchrutscht,
löst es echte Bestellungen bei echten Händlern aus. Diese Tests sind
deshalb bewusst paranoid und decken auch Schreibweisen ab, die im
Produktivcode gar nicht vorkommen sollten.

Vier Schranken, vier Testgruppen:

1. **Beschriftungen** — `is_forbidden_label`. Was nach Kaufbutton aussieht,
   wird nicht geklickt.
2. **Felder** — `is_forbidden_field`. Was nach Zahlungs- oder Zugangsdaten
   aussieht, wird nicht befüllt. Auch nicht mit Testdaten.
3. **URLs** — `is_forbidden_url`. Was nach Bestellabschluss aussieht, wird
   nicht aufgerufen.
4. **Struktur** — `test_kein_ungeschuetzter_klick_im_beschaffungscode`. Es
   gibt keinen Klickpfad, der an Schranke 1 vorbeiführt.

Die vierte ist die wichtigste, weil sie die einzige ist, die auch das
abdeckt, woran niemand gedacht hat. Sie fand beim ersten Lauf drei echte
Umgehungen: in `adapters/base.py` (Varianten-Kacheln), in `shopware.py`
(Gastbestellung) und in `render.py` (Consent-Dialog).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from psp_radar.collect.adapters.base import (
    is_forbidden_field,
    is_forbidden_label,
    is_forbidden_url,
    safe_click,
    safe_fill,
)

# Beschriftungen, die eine Bestellung auslösen könnten. Keine davon
# darf jemals geklickt werden.
MUST_BLOCK = [
    "Zahlungspflichtig bestellen",
    "zahlungspflichtig bestellen",
    "ZAHLUNGSPFLICHTIG BESTELLEN",
    "Jetzt bestellen",
    "Jetzt kaufen",
    "Kaufen",
    "Zahlungspflichtig Bestellen »",
    "Bestellung abschließen",
    "Bestellung abschliessen",
    "Kostenpflichtig bestellen",
    "Place order",
    "Place Order",
    "Complete order",
    "Order now",
    "Pay now",
    "Buy now",
    "Confirm and pay",
    "Confirm & Pay",
    "Submit order",
    "  Jetzt   bestellen  ",
    "Weiter und zahlungspflichtig bestellen",
    "Zahlungspflichtig buchen",
    "Bestellung absenden",
    "Bestellung aufgeben",
    "Verbindlich bestellen",
    "Complete purchase",
    "Purchase now",
    # Nachträglich ergänzt. Jede Zeile hier war eine Lücke.
    "Kauf abschließen",
    "Jetzt zahlen",
    "Jetzt bezahlen",
    "Bestellung bestätigen",
    "Buchung abschließen",
    "Weiter und bezahlen",
    "Review and pay",
    "Complete payment",
    "Jetzt buchen",
    "Newsletter abonnieren",
    "Jetzt spenden",
    # Allein stehend gefährlich, als Teil einer Phrase harmlos
    "Bestellen",
    "bestellen",
    "Bestellen »",
    "  Kaufen  ",
    "Bezahlen",
    "Zahlen",
    "Bestätigen",
    "Absenden",
    "Order",
    "Pay",
    "Buy",
    "Confirm",
]

# Beschriftungen, die geklickt werden dürfen — sie bringen uns zur
# Zahlungsauswahl, lösen aber nichts aus.
MUST_ALLOW = [
    "In den Warenkorb",
    "Zur Kasse",
    "Weiter",
    "Weiter zur Zahlung",
    "Zur Zahlungsart",
    "Als Gast bestellen",
    "Continue to payment",
    "Add to cart",
    "Alle akzeptieren",
    "Weiter zur Übersicht",
    "Versandart wählen",
]


@pytest.mark.parametrize("label", MUST_BLOCK)
def test_kaufausloesende_labels_werden_blockiert(label: str) -> None:
    assert is_forbidden_label(label), f"GEFAHR: {label!r} würde geklickt werden"


@pytest.mark.parametrize("label", MUST_ALLOW)
def test_harmlose_labels_bleiben_erlaubt(label: str) -> None:
    assert not is_forbidden_label(label), f"{label!r} wird unnötig blockiert"


def test_gast_bestellen_ist_erlaubt_aber_jetzt_bestellen_nicht() -> None:
    """Der Unterschied zwischen 'Als Gast bestellen' und 'Jetzt bestellen'.

    Beide enthalten 'bestellen'. Nur eines davon kostet Geld. Eine naive
    Substring-Prüfung auf 'bestellen' würde entweder zu viel blockieren
    oder zu wenig — deshalb wird auf Phrasen geprüft, nicht auf Wörter.
    """
    assert not is_forbidden_label("Als Gast bestellen")
    assert is_forbidden_label("Jetzt bestellen")
    assert is_forbidden_label("Bestellung abschließen")


def test_sperrliste_ist_nicht_leer() -> None:
    """Schutz davor, dass die Sperrliste versehentlich geleert wird."""
    from psp_radar.config import FORBIDDEN_SUBMIT_PATTERNS

    assert len(FORBIDDEN_SUBMIT_PATTERNS) >= 10


def test_gleiche_beschriftung_in_mehreren_attributen_bleibt_gesperrt() -> None:
    """Der Fall, an dem die alte Fassung vorbeigelaufen wäre.

    `safe_click` liest Text, `value`, `aria-label` und `title` und fügte sie
    früher zu **einer** Zeichenkette zusammen. Ein Button mit Text
    "Bestellen" und `aria-label="Bestellen"` ergab damit "Bestellen
    Bestellen" — was in keiner Sperrliste steht und geklickt worden wäre.
    Jedes Stück wird deshalb auch einzeln geprüft.
    """
    assert is_forbidden_label("Bestellen", "Bestellen")
    assert is_forbidden_label("", "Bestellen", "")
    assert is_forbidden_label("Weiter\nBestellen")
    assert not is_forbidden_label("Als Gast bestellen", "Als Gast bestellen")


# ---------------------------------------------------------------------------
# Schranke 1: kein Klick ohne prüfbare Beschriftung
# ---------------------------------------------------------------------------


class FakeLocator:
    """Minimaler Ersatz für einen Playwright-Locator.

    Damit lässt sich `safe_click` **im Verhalten** testen statt nur im
    Quelltext. Der vorherige Test prüfte per `inspect.getsource`, ob der
    Funktionsname `is_forbidden_label` im Code vorkommt — das hätte auch ein
    Kommentar erfüllt, und es hat die eigentliche Lücke nicht gefunden.
    """

    def __init__(
        self,
        *,
        text: str = "",
        attrs: dict[str, str] | None = None,
        visible: bool = True,
    ) -> None:
        self.text = text
        self.attrs = attrs or {}
        self.visible = visible
        self.clicked = False
        self.filled: str | None = None

    @property
    def first(self) -> FakeLocator:
        return self

    def locator(self, _selector: str) -> FakeLocator:
        return FakeLocator(visible=False)

    async def count(self) -> int:
        return 0

    async def is_visible(self, timeout: Any = None) -> bool:
        return self.visible

    async def inner_text(self, timeout: Any = None) -> str:
        return self.text

    async def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)

    async def click(self, timeout: Any = None) -> None:
        self.clicked = True

    async def fill(self, value: str, timeout: Any = None) -> None:
        self.filled = value


@pytest.mark.asyncio
async def test_element_ohne_beschriftung_wird_nicht_geklickt() -> None:
    """Ein Icon-Button ohne jeden Text darf nicht geklickt werden.

    Das stand so in der Dokumentation ("Ohne ermittelbaren Text wird nicht
    geklickt"), aber nicht im Code: Waren Text, `value`, `aria-label` und
    `title` alle leer, ergab das eine leere Beschriftung — und eine leere
    Beschriftung löste keine Sperre aus. Bei einem Kaufbutton, der nur ein
    Warenkorb-Icon zeigt, wäre das eine Bestellung gewesen.
    """
    stumm = FakeLocator(text="", attrs={})
    assert await safe_click(stumm) is False  # type: ignore[arg-type]
    assert not stumm.clicked, "GEFAHR: Element ohne Beschriftung wurde geklickt"


@pytest.mark.asyncio
async def test_beschriftung_aus_alt_text_genuegt() -> None:
    """Damit die Notbremse nicht jeden harmlosen Icon-Button blockiert."""
    icon = FakeLocator(text="", attrs={"aria-label": "In den Warenkorb"})
    assert await safe_click(icon) is True  # type: ignore[arg-type]
    assert icon.clicked


@pytest.mark.asyncio
async def test_kaufbutton_wird_auch_bei_nur_einem_attribut_gestoppt() -> None:
    for attribut in ("value", "aria-label", "title", "data-testid"):
        knopf = FakeLocator(text="", attrs={attribut: "Zahlungspflichtig bestellen"})
        assert await safe_click(knopf) is False  # type: ignore[arg-type]
        assert not knopf.clicked, f"GEFAHR: Kaufbutton über {attribut} geklickt"


# ---------------------------------------------------------------------------
# Schranke 2: keine Zahlungsdaten
# ---------------------------------------------------------------------------

ZAHLUNGSFELDER = [
    {"name": "cardNumber"},
    {"name": "cc-number"},
    {"id": "kartennummer"},
    {"autocomplete": "cc-number"},
    {"autocomplete": "cc-exp"},
    {"name": "cvc"},
    {"name": "cvv"},
    {"placeholder": "Prüfnummer"},
    {"aria-label": "Kreditkarte"},
    {"name": "iban"},
    {"name": "bic"},
    {"name": "kontonummer"},
    {"name": "expiryMonth"},
    {"name": "sepa_mandate"},
    {"type": "password"},
    {"name": "password"},
    {"name": "passwort"},
]

ADRESSFELDER = [
    {"name": "billing_first_name"},
    {"name": "personalMail"},
    {"name": "oxstreet"},
    {"name": "billingAddress[zipcode]"},
    {"name": "city"},
    {"type": "email", "name": "email"},
]


@pytest.mark.parametrize("attrs", ZAHLUNGSFELDER)
@pytest.mark.asyncio
async def test_zahlungsfelder_werden_nicht_befuellt(attrs: dict[str, str]) -> None:
    """Auch nicht mit Testdaten.

    Ein Testeintrag in einem Kartenfeld sieht für den Shop und seinen PSP
    wie ein Zahlungsversuch aus. Er kann eine Autorisierung anstossen, eine
    Betrugsprüfung auslösen oder eine Karte sperren — alles Folgen bei
    Dritten, für die es keinen Grund gibt.
    """
    feld = FakeLocator(attrs=attrs)
    assert await safe_fill(feld, "4111111111111111") is False  # type: ignore[arg-type]
    assert feld.filled is None, f"GEFAHR: {attrs} wurde befüllt"


@pytest.mark.parametrize("attrs", ADRESSFELDER)
@pytest.mark.asyncio
async def test_adressfelder_bleiben_befuellbar(attrs: dict[str, str]) -> None:
    """Ohne Adresse erscheint die Zahlungsauswahl nicht — das muss gehen."""
    feld = FakeLocator(attrs=attrs)
    assert await safe_fill(feld, "Teststrasse 1") is True  # type: ignore[arg-type]
    assert feld.filled == "Teststrasse 1"


def test_feldsperre_deckt_die_ueblichen_namen_ab() -> None:
    assert is_forbidden_field(("", "", "cc-number", "", "", "text"))
    assert not is_forbidden_field(("billing_city", "", "address-level2", "Ort", "", "text"))


# ---------------------------------------------------------------------------
# Schranke 3: keine Bestellabschluss-URLs
# ---------------------------------------------------------------------------

VERBOTENE_URLS = [
    "https://shop.de/checkout/finish",
    "https://shop.de/checkout/place-order",
    "https://shop.de/order/submit",
    "https://shop.de/index.php?cl=order",
    "https://shop.de/?cl=thankyou",
    "https://shop.de/checkout/order-received/1234/",
    "https://shop.de/place_order",
    "https://shop.de/bestellung/abschliessen",
    "https://shop.de/thank-you-for-your-order",
]

ERLAUBTE_URLS = [
    "https://shop.de/",
    "https://shop.de/warenkorb/",
    "https://shop.de/checkout/cart",
    "https://shop.de/checkout/confirm",
    "https://shop.de/checkout/shippingPayment",
    "https://shop.de/kasse",
    "https://shop.de/index.php?cl=user",
    "https://shop.de/lieferung-und-zahlung/",
]


@pytest.mark.parametrize("url", VERBOTENE_URLS)
def test_bestellabschluss_urls_werden_nicht_aufgerufen(url: str) -> None:
    """Auch nicht per GET.

    Die Adapter raten Checkout-Pfade, weil jedes Shopsystem andere
    verwendet. Eine Warenkorb- oder Adressseite zu öffnen ist unbedenklich,
    sie zeigt nur an. Ein geratener Pfad wie `/checkout/finish` ist etwas
    anderes: Ein sauber gebauter Shop schliesst keine Bestellung auf ein GET
    ab, aber sich darauf zu verlassen, dass fremder Code sauber gebaut ist,
    ist keine Sicherheitsmassnahme.
    """
    assert is_forbidden_url(url), f"GEFAHR: {url} würde aufgerufen"


@pytest.mark.parametrize("url", ERLAUBTE_URLS)
def test_anzeigeseiten_bleiben_erreichbar(url: str) -> None:
    assert not is_forbidden_url(url), f"{url} wird unnötig blockiert"


def test_shopware_bestaetigungsseite_bleibt_erreichbar_der_abschluss_nicht() -> None:
    """Der feine Unterschied, auf den es bei Shopware ankommt.

    `/checkout/confirm` ist die Übersicht — sie zeigt den Kaufbutton, löst
    aber nichts aus, und sie ist die Seite, auf der die Zahlungsarten
    stehen. `/checkout/finish` ist die Seite **nach** der Bestellung.
    """
    assert not is_forbidden_url("https://shop.de/checkout/confirm")
    assert is_forbidden_url("https://shop.de/checkout/finish")


# ---------------------------------------------------------------------------
# Schranke 4: kein Klickpfad an der Prüfung vorbei
# ---------------------------------------------------------------------------

#: Zustandsverändernde Playwright-Aufrufe, die eine Bestellung auslösen
#: können. `select_option` fehlt bewusst: Eine Variantenauswahl verändert
#: nichts beim Händler, und ohne sie bleibt der Warenkorb-Button gesperrt.
GEFAEHRLICHE_AUFRUFE = frozenset(
    {"click", "dblclick", "tap", "press", "press_sequentially", "check", "set_checked", "fill"}
)

#: Die einzigen Stellen, an denen geklickt und ausgefüllt werden darf — dort
#: sitzen die Prüfungen.
ERLAUBT = {
    ("collect/adapters/base.py", "safe_click", "click"),
    ("collect/adapters/base.py", "safe_fill", "fill"),
}

QUELLE = Path(__file__).resolve().parents[1] / "src" / "psp_radar"


def _aufrufe(datei: Path) -> list[tuple[str, str, int]]:
    """Findet zustandsverändernde Aufrufe samt umgebender Funktion."""
    baum = ast.parse(datei.read_text(encoding="utf-8"))
    treffer: list[tuple[str, str, int]] = []

    class Besucher(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _funktion(self, node: ast.AST) -> None:
            self.stack.append(getattr(node, "name", "?"))
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._funktion(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._funktion(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr in GEFAEHRLICHE_AUFRUFE:
                treffer.append(
                    (self.stack[-1] if self.stack else "<modul>", node.func.attr, node.lineno)
                )
            self.generic_visit(node)

    Besucher().visit(baum)
    return treffer


def test_kein_ungeschuetzter_klick_im_beschaffungscode() -> None:
    """Es darf keinen Klick geben, der an `safe_click` vorbeiführt.

    Das ist die einzige Schranke, die auch das abdeckt, woran niemand
    gedacht hat. Beim ersten Lauf fand sie drei echte Umgehungen:

    - `adapters/base.py::_select_required_variants` — Varianten-Kacheln
    - `adapters/shopware.py::fill_guest_details` — Gastbestellung aktivieren
    - `collect/render.py::_dismiss_cookie_banner` — Consent-Dialog

    Alle drei waren in der Praxis harmlos: Ein Consent-Button bestellt
    nichts. Aber alle drei nutzten breite Selektoren wie
    `fieldset label:not([class*='disabled'])`, und was so ein Selektor auf
    einem unbekannten Shop trifft, weiss man vorher nicht.
    """
    verstoesse: list[str] = []
    for datei in sorted(QUELLE.rglob("*.py")):
        relativ = datei.relative_to(QUELLE).as_posix()
        for funktion, aufruf, zeile in _aufrufe(datei):
            if (relativ, funktion, aufruf) in ERLAUBT:
                continue
            verstoesse.append(f"{relativ}:{zeile} in {funktion}() → .{aufruf}()")

    assert not verstoesse, (
        "Klick ausserhalb von safe_click gefunden:\n  "
        + "\n  ".join(verstoesse)
        + "\n\nJeder Klick muss über safe_click laufen, sonst greift die "
        "Sperrliste nicht."
    )


def test_kein_klick_in_eingebettetem_javascript() -> None:
    """Auch `page.evaluate("...button.click()...")` umgeht die Prüfung.

    Der AST sieht nicht in Zeichenketten hinein. Ein Klick in eingebettetem
    JavaScript wäre also unsichtbar für den Test darüber — und würde die
    Sperrliste vollständig umgehen. Die Beschaffungsschicht nutzt
    `page.evaluate` für Lesezugriffe und für Shopifys Cart-API; klicken darf
    sie darin nicht.
    """
    verstoesse: list[str] = []
    for datei in sorted((QUELLE / "collect").rglob("*.py")):
        for text, zeile in _zeichenketten(datei):
            if ".click(" in text or ".submit(" in text:
                verstoesse.append(f"{datei.relative_to(QUELLE).as_posix()}:{zeile}")

    assert not verstoesse, f"Klick in eingebettetem JavaScript: {verstoesse}"


def _zeichenketten(datei: Path) -> list[tuple[str, int]]:
    """Alle String-Literale einer Datei — ohne Docstrings.

    Docstrings müssen draussen bleiben, sonst löst dieser Test bei jeder
    Erklärung aus, die den Fehler beschreibt, den er verhindert. Genau das
    passierte beim ersten Lauf: Die Modulbeschreibung von `base.py` erwähnt
    `element.click()` als Beispiel für die gefundene Umgehung.
    """
    baum = ast.parse(datei.read_text(encoding="utf-8"))

    docstrings: set[int] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            koerper = getattr(knoten, "body", [])
            if (
                koerper
                and isinstance(koerper[0], ast.Expr)
                and isinstance(koerper[0].value, ast.Constant)
                and isinstance(koerper[0].value.value, str)
            ):
                docstrings.add(id(koerper[0].value))

    return [
        (knoten.value, knoten.lineno)
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Constant)
        and isinstance(knoten.value, str)
        and id(knoten) not in docstrings
    ]


def test_sperrlisten_sind_nicht_leer() -> None:
    """Schutz davor, dass eine Sperrliste versehentlich geleert wird."""
    from psp_radar.config import (
        FORBIDDEN_FIELD_PATTERNS,
        FORBIDDEN_STANDALONE_LABELS,
        FORBIDDEN_SUBMIT_PATTERNS,
        FORBIDDEN_URL_PATTERNS,
    )

    assert len(FORBIDDEN_SUBMIT_PATTERNS) >= 25
    assert len(FORBIDDEN_STANDALONE_LABELS) >= 15
    assert len(FORBIDDEN_FIELD_PATTERNS) >= 15
    assert len(FORBIDDEN_URL_PATTERNS) >= 10
