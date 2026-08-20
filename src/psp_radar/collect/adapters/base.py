"""Basis für Checkout-Adapter — und der Ort, an dem die Sicherheitsschranken sitzen.

Jeder Shop ist anders gebaut, aber der Ablauf ist überall derselbe:
Produkt öffnen → in den Warenkorb → zum Checkout → Adresse ausfüllen →
Zahlungsauswahl. Diese Klasse implementiert den Ablauf generisch mit
robusten Heuristiken; Plattform-Adapter überschreiben nur, was ihr System
anders macht.

## Die vier Schranken

Sicherheitsregel für alle Adapter, nicht umgehbar: **Es wird nie eine
Bestellung ausgelöst, es werden nie Zahlungsdaten eingegeben.** Ziel ist die
Seite mit der Zahlungsauswahl — dort ist Schluss.

Durchgesetzt wird das an vier Stellen, jede mit eigenem Wächter in
`tests/test_safety.py`:

1. `safe_click` — prüft die Beschriftung vor jedem Klick. Ohne ermittelbare
   Beschriftung wird nicht geklickt.
2. `safe_fill` — verweigert Felder, die nach Zahlungs- oder Zugangsdaten
   aussehen. Auch für Testdaten.
3. `safe_goto` — navigiert nie auf eine URL, die nach Bestellabschluss
   aussieht.
4. `test_safety.py::test_kein_ungeschuetzter_klick_im_beschaffungscode` —
   verbietet strukturell, dass irgendwo im Beschaffungscode an `safe_click`
   vorbei geklickt wird.

Punkt 4 ist der wichtigste. Die ersten drei schützen vor den Klicks, an die
jemand gedacht hat; Punkt 4 schützt vor denen, an die niemand gedacht hat.
Er entstand aus einem Befund: In dieser Datei, in `shopware.py` und in
`render.py` stand je ein `element.click()` an `safe_click` vorbei.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from ...config import (
    FORBIDDEN_FIELD_PATTERNS,
    FORBIDDEN_STANDALONE_LABELS,
    FORBIDDEN_SUBMIT_PATTERNS,
    FORBIDDEN_URL_PATTERNS,
    ScanConfig,
)
from ..waiting import (
    read_cart_count,
    wait_for_cart_change,
    wait_for_selector_any,
    wait_for_text,
    wait_for_url_change,
    wait_until,
)

_FORBIDDEN = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_SUBMIT_PATTERNS)
_FORBIDDEN_FIELDS = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_FIELD_PATTERNS)
_FORBIDDEN_URLS = tuple(re.compile(p, re.IGNORECASE) for p in FORBIDDEN_URL_PATTERNS)
_STANDALONE = frozenset(label.lower() for label in FORBIDDEN_STANDALONE_LABELS)

#: Zeichen, die eine Beschriftung schmücken, ohne ihre Bedeutung zu ändern.
#: "Bestellen »" und "› BESTELLEN" sind derselbe Button.
_DEKOR = re.compile(r"^[\s »«›‹→←⇒>\-–—*·•+_.:|\[\]()]+|[\s »«›‹→←⇒>\-–—*·•+_.:|\[\]()!]+$")


def _segmente(texts: tuple[str, ...]) -> list[str]:
    """Zerlegt Beschriftungen in einzeln prüfbare Stücke.

    Nötig, weil `safe_click` mehrere Quellen liest — Text, `value`,
    `aria-label`, `title`. Ein Button mit Text "Bestellen" **und**
    `aria-label="Bestellen"` ergäbe zusammengesetzt "Bestellen Bestellen",
    und das steht in keiner Sperrliste. Also wird jedes Stück auch für sich
    geprüft.
    """
    stuecke: list[str] = []
    for text in texts:
        if not text:
            continue
        stuecke.append(text)
        # Mehrzeilige Buttons und Trennzeichen: jede Zeile ist eine Aussage
        stuecke.extend(re.split(r"[\n\r\t|•·]+", text))
    return stuecke


def _normalisiert(text: str) -> str:
    ohne_dekor = _DEKOR.sub("", text)
    return re.sub(r"\s+", " ", ohne_dekor).strip().lower()


def is_forbidden_label(*texts: str) -> bool:
    """Ob eine Beschriftung auf einen kaufauslösenden Button hindeutet.

    Zwei Prüfungen mit unterschiedlicher Logik:

    - **Musterprüfung** auf Vorkommen. "Weiter und zahlungspflichtig
      bestellen" enthält "pflichtig" und ist damit erledigt.
    - **Vollvergleich** gegen `FORBIDDEN_STANDALONE_LABELS`. Nötig für die
      Fälle, in denen dasselbe Wort harmlos oder gefährlich ist, je nachdem
      ob noch etwas daneben steht: "Als Gast bestellen" muss geklickt
      werden, ein Button mit nur "Bestellen" nicht.
    """
    stuecke = _segmente(texts)
    if any(rx.search(stueck) for stueck in stuecke for rx in _FORBIDDEN):
        return True
    return any(_normalisiert(stueck) in _STANDALONE for stueck in stuecke)


def is_forbidden_url(url: str) -> bool:
    """Ob eine URL nach Bestellabschluss aussieht."""
    return any(rx.search(url) for rx in _FORBIDDEN_URLS)


def is_forbidden_field(attributes: tuple[str, ...]) -> bool:
    """Ob ein Formularfeld nach Zahlungs- oder Zugangsdaten aussieht."""
    return any(rx.search(attr) for attr in attributes if attr for rx in _FORBIDDEN_FIELDS)


async def _beschriftung(locator: Locator, timeout: float) -> tuple[str, ...]:
    """Sammelt alles, was als Beschriftung durchgeht.

    Bewusst breit: Je mehr Text ermittelbar ist, desto seltener greift die
    Notbremse "ohne Text kein Klick" bei einem harmlosen Icon-Button — und
    desto zuverlässiger greift sie bei einem gefährlichen.
    """
    teile = [
        (await locator.inner_text(timeout=timeout) or ""),
        await locator.get_attribute("value") or "",
        await locator.get_attribute("aria-label") or "",
        await locator.get_attribute("title") or "",
        await locator.get_attribute("name") or "",
        await locator.get_attribute("data-testid") or "",
        # OXID legt die Variantenbezeichnung hierhin ("Black", "M"). Eine
        # Farbkachel hat oft keinen sichtbaren Text, und ohne Beschriftung
        # klickt safe_click nicht — dann bleibt der Warenkorb-Button gesperrt.
        await locator.get_attribute("data-varsel") or "",
    ]
    try:
        bild = locator.locator("img[alt]").first
        if await bild.count():
            teile.append(await bild.get_attribute("alt") or "")
    except PlaywrightError:
        pass
    return tuple(t for t in teile if t and t.strip())


async def safe_click(locator: Locator, timeout: float = 5.0) -> bool:
    """Klickt ein Element — aber nur, wenn es garantiert nichts bestellt.

    Die Beschriftung wird vorher gelesen und gegen die Sperrliste geprüft.
    **Lässt sich keine Beschriftung ermitteln, wird nicht geklickt.** Das
    stand vorher so in der Dokumentation, aber nicht im Code: Ein Element
    ohne Text, `value`, `aria-label` und `title` ergab eine leere
    Beschriftung, die keine Sperre auslöste — und wurde geklickt. Bei einem
    Kaufbutton, der nur ein Icon zeigt, wäre das eine Bestellung gewesen.

    Im Zweifel lieber ein verpasstes Signal als eine ausgelöste Bestellung.
    """
    try:
        if not await locator.is_visible(timeout=timeout * 1000):
            return False
        teile = await _beschriftung(locator, timeout=2000)
    except PlaywrightError:
        return False

    if not teile:
        return False
    if is_forbidden_label(*teile):
        return False

    try:
        await locator.click(timeout=timeout * 1000)
        return True
    except PlaywrightError:
        return False


async def try_selectors(page: Page, selectors: tuple[str, ...], timeout: float = 3.0) -> bool:
    """Probiert Selektoren der Reihe nach und klickt den ersten passenden."""
    for selector in selectors:
        try:
            if await safe_click(page.locator(selector).first, timeout=timeout):
                return True
        except PlaywrightError:
            continue
    return False


async def safe_fill(field: Locator, value: str, *, timeout: float = 3.0) -> bool:
    """Füllt ein Feld — aber nie ein Zahlungs- oder Zugangsdatenfeld.

    Der Gast-Checkout braucht Adressdaten, sonst erscheint die
    Zahlungsauswahl nicht. Kartennummer, IBAN, CVC und Passwörter braucht er
    nicht, und sie werden auch nicht mit Testdaten befüllt: Ein Testeintrag
    in einem Kartenfeld sieht für den Shop wie ein Zahlungsversuch aus.
    """
    try:
        if not await field.is_visible(timeout=timeout * 400):
            return False
        attribute = [
            (await field.get_attribute(name) or "")
            for name in ("name", "id", "autocomplete", "placeholder", "aria-label", "type")
        ]
    except PlaywrightError:
        return False

    if is_forbidden_field(tuple(attribute)):
        return False
    if attribute[5].lower() == "password":
        return False

    try:
        await field.fill(value, timeout=timeout * 1000)
        return True
    except PlaywrightError:
        return False


async def fill_first(page: Page, selectors: tuple[str, ...], value: str) -> bool:
    """Füllt das erste sichtbare Feld aus der Selektorliste."""
    for selector in selectors:
        try:
            if await safe_fill(page.locator(selector).first, value):
                return True
        except PlaywrightError:
            continue
    return False


async def safe_goto(page: Page, url: str, *, timeout: float = 25.0) -> bool:
    """Navigiert — aber nie auf eine URL, die nach Bestellabschluss aussieht.

    Die Adapter raten Checkout-Pfade, weil jedes Shopsystem andere verwendet.
    Raten ist dort vertretbar: Eine Warenkorb- oder Adressseite zeigt nur
    an. Ein geratener Pfad wie `/checkout/finish` wäre etwas anderes. Ein
    sauber gebauter Shop schliesst keine Bestellung auf ein GET ab — aber
    sich darauf zu verlassen, dass fremder Code sauber gebaut ist, ist keine
    Sicherheitsmassnahme.
    """
    if is_forbidden_url(url):
        return False
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        return True
    except PlaywrightError:
        return False


class CheckoutAdapter:
    """Generischer Adapter — greift, wenn keine Plattform erkannt wurde."""

    #: Plattform-ID aus platforms.yaml, für die dieser Adapter zuständig ist
    platform_id: str | None = None
    name: str = "generisch"

    # Alle Selektorlisten sind als `tuple[str, ...]` deklariert, nicht als
    # Tuple fester Länge. Sonst gilt für mypy die Länge der Liste in dieser
    # Klasse als Teil des Typs, und jeder Adapter, der eine kürzere Liste
    # mitbringt, erzeugt einen Typfehler — 12 Meldungen, die alle nichts
    # bedeuten und die echten übertönen.

    #: Reihenfolge nach Verlässlichkeit. Ganz oben stehen Attribute, die
    #: Shops für ihre eigenen automatisierten Tests vergeben — die sind
    #: deutlich stabiler als CSS-Klassen, weil sie einen Umbau des Designs
    #: überleben. Bei bergfreunde.de etwa `data-codecept="toBasket"`, was
    #: keiner der klassenbasierten Selektoren gefunden hätte.
    ADD_TO_CART: tuple[str, ...] = (
        "[data-codecept*='toBasket' i]",
        "[data-testid*='add-to-cart' i]",
        "[data-testid*='addtocart' i]",
        "[data-test*='add-to-cart' i]",
        "[id*='addToCart' i]",
        "[id*='toBasket' i]",
        "button[name='add']",
        "button[name='tobasket']",
        "form[action*='cart'] button[type='submit']",
        "button[aria-label*='Warenkorb' i]",
        "button:has-text('In den Warenkorb')",
        "button:has-text('In den Einkaufswagen')",
        "button:has-text('Zum Warenkorb hinzufügen')",
        "button:has-text('Add to cart')",
        "button:has-text('Add to bag')",
        "a:has-text('In den Warenkorb')",
        "[class*='add-to-cart'] button",
        "button[class*='addtocart' i]",
        "input[value*='Warenkorb' i]",
    )

    CART_URLS: tuple[str, ...] = ("/cart", "/warenkorb", "/checkout/cart", "/basket")

    TO_CHECKOUT: tuple[str, ...] = (
        "a[href*='checkout']:visible",
        "button:has-text('Zur Kasse')",
        "a:has-text('Zur Kasse')",
        "button:has-text('Weiter zur Kasse')",
        "button:has-text('Checkout')",
        "a:has-text('Checkout')",
        "button:has-text('Zur Bestellung')",
        "[data-testid*='checkout']",
    )

    GUEST_CHECKOUT: tuple[str, ...] = (
        "button:has-text('Als Gast')",
        "a:has-text('Als Gast')",
        "label:has-text('Als Gast bestellen')",
        "input[value='guest']",
        "button:has-text('Ohne Konto')",
        "button:has-text('Continue as guest')",
    )

    EMAIL: tuple[str, ...] = ("input[type='email']", "input[name*='email' i]", "#email")
    FIRST_NAME: tuple[str, ...] = ("input[name*='firstname' i]", "input[name*='first_name' i]", "input[id*='firstName' i]")
    LAST_NAME: tuple[str, ...] = ("input[name*='lastname' i]", "input[name*='last_name' i]", "input[id*='lastName' i]")
    STREET: tuple[str, ...] = ("input[name*='street' i]", "input[name*='address1' i]", "input[name*='address' i]")
    ZIP: tuple[str, ...] = ("input[name*='zip' i]", "input[name*='postal' i]", "input[name*='plz' i]")
    CITY: tuple[str, ...] = ("input[name*='city' i]", "input[name*='ort' i]")

    CONTINUE: tuple[str, ...] = (
        "button:has-text('Weiter'):not(:has-text('bestellen'))",
        "button:has-text('Weiter zur Zahlung')",
        "button:has-text('Zur Zahlungsart')",
        "button:has-text('Continue to payment')",
        "button:has-text('Continue to shipping')",
        "button[type='submit']:not([name*='order'])",
    )

    #: Woran erkennen wir, dass die Zahlungsauswahl erreicht ist?
    PAYMENT_MARKERS: tuple[str, ...] = (
        "kreditkarte",
        "zahlungsart",
        "zahlungsmethode",
        "zahlungsweise",
        "payment method",
        "rechnungskauf",
        "sepa-lastschrift",
        "vorkasse",
        "zahlungsoptionen",
    )

    #: Sichtbare Bestätigung, dass der Warenkorb den Artikel aufgenommen hat.
    #: Bewusst spezifisch: Das Wort "Warenkorb" allein steht in jedem Header
    #: und wäre als Erfolgsmeldung wertlos.
    CART_SUCCESS_MARKERS: tuple[str, ...] = (
        "in den warenkorb gelegt",
        "wurde in den warenkorb",
        "zum warenkorb hinzugefügt",
        "artikel wurde hinzugefügt",
        "erfolgreich hinzugefügt",
        "added to cart",
        "added to your cart",
        "added to bag",
    )

    #: Marker für einen leeren Warenkorb. Absichtlich als Phrase, nicht als
    #: Wort: "leer" steht auch in "Leergut" und "Leerlauf".
    CART_EMPTY_MARKERS: tuple[str, ...] = (
        "warenkorb ist leer",
        "warenkorb ist noch leer",
        "keine artikel im warenkorb",
        "ihr einkaufswagen ist leer",
        "cart is empty",
        "your basket is empty",
        "no items in your cart",
    )

    # ------------------------------------------------------------------

    async def add_to_cart(self, page: Page, config: ScanConfig) -> bool:
        """Legt das aktuell geöffnete Produkt in den Warenkorb.

        Mit Erfolgskontrolle: Ein Klick, der nichts bewirkt hat — etwa weil
        eine Pflichtvariante fehlte —, gilt nicht als Erfolg. Ohne diese
        Prüfung läuft die Simulation ins Leere weiter und meldet am Ende
        einen Checkout, den es nie gegeben hat.
        """
        vorher = await read_cart_count(page)
        await self._select_required_variants(page)

        if not await try_selectors(page, self.ADD_TO_CART, timeout=4.0):
            return False

        return await self.cart_grew(page, vorher)

    async def cart_grew(self, page: Page, before: int) -> bool:
        """Prüft, ob der Klick den Warenkorb tatsächlich gefüllt hat.

        Drei Wege, absteigend nach Verlässlichkeit: gezählte Artikel,
        sichtbare Erfolgsmeldung, Zähler überhaupt grösser null. Findet
        keiner etwas, lautet die Antwort nein — auch wenn der Klick
        funktioniert haben könnte. `go_to_cart` prüft danach ohnehin noch
        einmal am Warenkorb selbst.
        """
        if before >= 0 and await wait_for_cart_change(page, before, timeout=10.0):
            return True
        if await wait_for_text(page, self.CART_SUCCESS_MARKERS, timeout=6.0):
            return True
        return await read_cart_count(page) > 0

    async def _select_required_variants(self, page: Page) -> None:
        """Wählt Pflichtvarianten (Grösse, Farbe) vor, sonst blockt der Button.

        Bei Bekleidungsshops die häufigste Ursache dafür, dass "In den
        Warenkorb" nichts tut.
        """
        try:
            # Filter- und Sortierfelder ausdrücklich ausschliessen. Auf
            # bergfreunde.de sind die einzigen beiden `<select>` einer
            # Produktseite `streamfilter[sort]` und `streamfilter[type]`;
            # eine Option darin auszuwählen lädt die Seite neu, und damit
            # ist die Produktseite weg, bevor der Warenkorb-Klick kommt.
            selects = page.locator(
                "select[required], "
                "form select:not([name*='filter' i]):not([id*='filter' i]):not([name*='sort' i])"
            )
            count = min(await selects.count(), 4)
            for index in range(count):
                select = selects.nth(index)
                if not await select.is_visible(timeout=800):
                    continue
                options = await select.locator("option").all()
                for option in options[1:]:
                    value = await option.get_attribute("value")
                    disabled = await option.get_attribute("disabled")
                    if value and disabled is None:
                        await select.select_option(value, timeout=2500)
                        break
        except PlaywrightError:
            pass

        # Varianten als Kacheln, Schalter oder Farbfelder. Die Reihenfolge
        # geht von "eindeutig eine Variante" zu "vermutlich eine Variante";
        # geklickt wird nur die erste, die anspringt.
        for selector in (
            "[class*='variant'] button:not([disabled]):not([class*='disabled'])",
            "[class*='swatch'] input:not([disabled])",
            "[class*='swatch'] label:not([class*='disabled'])",
            "[data-variant]:not([disabled]):not([class*='soldout'])",
            "[class*='size'] li:not([class*='disabled']) a",
            "fieldset label:not([class*='disabled'])",
        ):
            try:
                element = page.locator(selector).first
                if await safe_click(element, timeout=1.5):
                    await wait_until(lambda: self._button_frei(page), timeout=3.0)
                    return
            except PlaywrightError:
                continue

    async def _button_frei(self, page: Page) -> bool:
        """Ob ein Warenkorb-Button jetzt anklickbar ist.

        Die Bedingung, auf die nach der Variantenwahl gewartet wird — statt
        auf eine geratene Sekundenzahl. Bei Shops, die den Button erst nach
        einem AJAX-Aufruf freigeben, war ein `sleep(0.6)` regelmässig zu
        kurz.
        """
        for selector in self.ADD_TO_CART[:6]:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=200) and await element.is_enabled(timeout=200):
                    return True
            except PlaywrightError:
                continue
        return False

    async def go_to_cart(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        """Öffnet den Warenkorb und prüft, ob wirklich etwas drin liegt.

        Der Rückgabewert ist eine Aussage über den Inhalt, nicht über die
        Erreichbarkeit der Seite. `checkout.py` verlässt sich darauf: Ein
        leerer Warenkorb bedeutet, dass der Klick vorher nichts bewirkt hat,
        und dann ist der weitere Weg sinnlos.
        """
        for path in self.CART_URLS:
            if not await safe_goto(page, urljoin(base_url, path)):
                continue
            if await self.cart_has_items(page):
                return True
        return False

    async def cart_has_items(self, page: Page) -> bool:
        anzahl = await read_cart_count(page)
        if anzahl > 0:
            return True
        try:
            text = (await page.inner_text("body", timeout=5000)).lower()
        except PlaywrightError:
            return False
        if any(marker in text for marker in self.CART_EMPTY_MARKERS):
            return False
        # Zähler unbekannt, kein Leer-Hinweis: Warenkorbseite mit Inhalt
        return anzahl == -1 and any(k in text for k in ("warenkorb", "cart", "basket"))

    async def go_to_checkout(self, page: Page, base_url: str, config: ScanConfig) -> bool:
        vorher = page.url
        if await try_selectors(page, self.TO_CHECKOUT, timeout=4.0):
            await wait_for_url_change(page, vorher, timeout=12.0)
            if "checkout" in page.url.lower() or "kasse" in page.url.lower():
                return True
            if await self.at_checkout(page):
                return True

        for path in ("/checkout", "/kasse", "/checkout/onepage", "/checkout/confirm"):
            if not await safe_goto(page, urljoin(base_url, path), timeout=25.0):
                continue
            if "checkout" in page.url.lower() or "kasse" in page.url.lower():
                await self.at_checkout(page)
                return True
        return False

    async def at_checkout(self, page: Page) -> bool:
        """Ob eine Checkout-Seite geladen ist — Adress- oder Zahlungsschritt."""
        return await wait_for_text(
            page,
            (*self.PAYMENT_MARKERS, "rechnungsadresse", "lieferadresse", "versandart", "billing"),
            timeout=8.0,
        )

    async def fill_guest_details(self, page: Page, config: ScanConfig) -> bool:
        """Füllt einen Gast-Checkout mit erkennbar synthetischen Testdaten.

        Ausschliesslich Adressdaten. Zahlungsfelder werden von `safe_fill`
        abgewiesen, selbst wenn ein Selektor sie treffen würde.
        """
        if await try_selectors(page, self.GUEST_CHECKOUT, timeout=2.5):
            await wait_for_selector_any(page, self.EMAIL + self.LAST_NAME, timeout=6.0)

        filled = False
        filled |= await fill_first(page, self.EMAIL, config.dummy_email)
        filled |= await fill_first(page, self.FIRST_NAME, config.dummy_first_name)
        filled |= await fill_first(page, self.LAST_NAME, config.dummy_last_name)
        filled |= await fill_first(page, self.STREET, config.dummy_street)
        filled |= await fill_first(page, self.ZIP, config.dummy_zip)
        filled |= await fill_first(page, self.CITY, config.dummy_city)
        return filled

    async def advance(self, page: Page, config: ScanConfig, steps: int = 3) -> None:
        """Klickt sich Richtung Zahlungsauswahl vor — nie darüber hinaus."""
        for _ in range(steps):
            if await self.at_payment_selection(page):
                return
            vorher = page.url
            if not await try_selectors(page, self.CONTINUE, timeout=3.0):
                return
            # Entweder wechselt die Seite oder der Schritt lädt nach. Beides
            # ist eine Bedingung, auf die man warten kann.
            await wait_until(self._fortschritt(page, vorher), timeout=15.0)

    def _fortschritt(self, page: Page, previous_url: str) -> Callable[[], Awaitable[bool]]:
        """Baut die Wartebedingung "ein Schritt weiter" für eine feste URL.

        Als eigene Funktion, nicht als Lambda in der Schleife: Ein Lambda
        würde die Schleifenvariable erst beim Aufruf auslesen. Hier ist die
        URL beim Bauen gebunden, und die Bedingung bleibt lesbar.
        """

        async def bedingung() -> bool:
            if page.url.rstrip("/") != previous_url.rstrip("/"):
                return True
            return await self.at_payment_selection(page)

        return bedingung

    async def at_payment_selection(self, page: Page) -> bool:
        """Prüft, ob die Zahlungsauswahl sichtbar ist."""
        try:
            text = (await page.inner_text("body", timeout=5000)).lower()
        except PlaywrightError:
            return False
        return sum(marker in text for marker in self.PAYMENT_MARKERS) >= 2
