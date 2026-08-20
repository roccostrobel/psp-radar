# psp-radar — Projektkontext

Liest aus Shop-URLs Shop-System und Zahlungsarten — und, wo möglich, den Zahlungsabwickler. Schwerpunkt DACH. Nachfolger von `psp-detector`, das als Referenz unangetastet liegen bleibt.

**Die Reihenfolge im Satz oben ist die Produktaussage, nicht Zufall.** Shop-System und Zahlungsarten sind belegbar (8 von 8 geprüften Shops korrekt). Der Abwickler ist ohne Checkout-Beobachtung nur bei etwa einem Viertel der DACH-Shops bestimmbar — gemessen, siehe `docs/BEFUNDE.md`. Wer die Reihenfolge umdreht, verkauft ein Ergebnis, das das Werkzeug in drei von vier Fällen nicht liefern kann.

Zwei Anforderungen unterscheiden dieses Projekt vom Vorgänger:

1. **Teilbar ohne Installation** — interner Nutzen, Zugang per Link oder Codespace
2. **Schnell genug für Listen** — 50 bis 200 Shop-URLs pro Lauf

## Die eine Sache, die man verstanden haben muss

**Der PSP ist auf der Startseite unsichtbar.** Er lädt erst im Checkout. Empirisch belegt: `snocks.com` ohne Checkout-Simulation → Shop-System zu 100 % erkannt, PSP nicht ermittelbar. Mit Simulation → Shopify Payments zu 98 %.

### Korrektur einer falschen Annahme

Frühere Fassungen dieses Dokuments behaupteten, der CSP-Header sei „die unterschätzteste Quelle" und `frame-src https://*.adyen.com` sei „praktisch ein Geständnis". **Das ist widerlegt.** Messung über 15 DACH-Shops am 19.08.2026:

| Quelle | Treffer |
|---|---|
| CSP-Header überhaupt gesetzt | **1 von 15** |
| Gateway aus CSP ableitbar | **0 von 15** |
| Gateway aus preconnect/dns-prefetch | 3 von 15 (alle Shopify) |
| Gateway aus Zahlungsseitentext | 1 von 15 (bergfreunde → Unzer) |
| **Gateway aus der Kombination** | **4 von 15 = 27 %** |

Deutsche Shops setzen überwiegend keine Content-Security-Policy. Die Behauptung stand mehrfach im Projekt, ohne je geprüft worden zu sein — ein Lehrstück darüber, wie eine plausible Idee zur Tatsache wird, wenn niemand sie messt. Details in `docs/BEFUNDE.md`.

Wer das Kapitel neu aufschlagen will, muss zuerst messen, nicht argumentieren.

## Architektur

```
core/      reine Logik — kein Netzwerk, kein Browser, keine Seiteneffekte
collect/   Beschaffung: httpx, Playwright, Plattform-Adapter
batch/     Trichter, Worker-Pool, Cache
eval/      Golden-Set, Fixtures, Messung
api/       FastAPI mit Zugangscode
web/       Oberfläche im Unzer-Design
```

**`core` darf nichts aus den anderen Schichten importieren.** `tests/test_architecture.py` erzwingt das. Der Grund ist nicht Ordnungsliebe: Nur so bleibt die gesamte Erkennung offline und deterministisch gegen eingefrorene Fixtures prüfbar — und damit die Vorgabe „schneller ohne Qualitätsverlust" überhaupt überprüfbar.

Fixtures liegen gepackt (`tests/fixtures/*.json.gz`). Ungepackt sind es 5 bis 12 MB pro Shop, weil sie das vollständige HTML enthalten. Sie zu **kürzen** ist verboten: Genau eine HTML-Grenze hat bei bergfreunde.de den Satz mit dem Anbieternamen abgeschnitten (siehe Regel 7). Eine Fixture ohne den entscheidenden Teil misst nichts.

Der Offline-Lauf kostet gemessen **19 s pro Shop**, nicht „Sekunden". Ursache sind `html_regex`-Signale über mehrere Megabyte Quelltext. Ein doppelter Durchgang über die ganze Datenbank ist entfernt (`match_all(..., only_roles=(Role.PLATFORM,))` für die Plattformerkennung, 2 min → 58 s bei drei Shops). Der Rest ist offen.

## Unverhandelbare Regeln

### 1. Es wird nie eine Bestellung ausgelöst und nie ein Zahlungsdatum eingegeben

Vier Schranken, alle in `collect/adapters/base.py`, jede mit Wächter in `tests/test_safety.py` — dem wichtigsten Testfile im Projekt:

| Schranke | Prüft | Sperrliste |
|---|---|---|
| `safe_click` | Beschriftung vor jedem Klick. **Ohne ermittelbare Beschriftung kein Klick** | `FORBIDDEN_SUBMIT_PATTERNS`, `FORBIDDEN_STANDALONE_LABELS` |
| `safe_fill` | Feldattribute vor jedem Eintrag | `FORBIDDEN_FIELD_PATTERNS` |
| `safe_goto` | Ziel vor jeder Navigation | `FORBIDDEN_URL_PATTERNS` |
| `test_kein_ungeschuetzter_klick_im_beschaffungscode` | per AST: kein `.click()` ausserhalb `safe_click`, kein `.fill()` ausserhalb `safe_fill` | — |

**Die vierte ist die wichtigste.** Die ersten drei schützen vor den Klicks, an die jemand gedacht hat; die vierte vor denen, an die niemand gedacht hat. Sie fand bei ihrer Einführung drei echte Umgehungen: `base.py` (Varianten-Kacheln), `shopware.py` (Gastbestellung), `render.py` (Consent-Dialog). Alle drei in der Praxis harmlos, alle drei mit breiten Selektoren wie `fieldset label:not([class*='disabled'])` — was so ein Selektor auf einem unbekannten Shop trifft, weiss man vorher nicht.

Zwei Lücken, die genau diese Tests aufgedeckt haben und die als Muster gelten:

- **Leere Beschriftung galt als harmlos.** `safe_click` fügte Text, `value`, `aria-label` und `title` zu einer Zeichenkette zusammen. Waren alle leer, war sie leer, und eine leere Zeichenkette löst keine Sperre aus. Die Dokumentation behauptete das Gegenteil.
- **Dieselbe Beschriftung in zwei Attributen.** Text „Bestellen" plus `aria-label="Bestellen"` ergab zusammengesetzt „Bestellen Bestellen" — steht in keiner Sperrliste. Deshalb wird jedes Stück auch einzeln geprüft.

Beide Fälle haben dieselbe Form: Die Dokumentation beschrieb einen Schutz, den der Code nicht hatte. Wer hier etwas ändert, prüft das Verhalten, nicht den Quelltext — der alte Test las per `inspect.getsource`, ob ein Funktionsname vorkommt, und hätte auch ein Kommentar erfüllt.

Die Muster nutzen, dass § 312j Abs. 3 BGB für deutsche Kaufbuttons eine eindeutige Beschriftung vorschreibt — praktisch jeder enthält „pflichtig". Diese Listen dürfen **nur erweitert, nie gekürzt** werden.

`FORBIDDEN_STANDALONE_LABELS` wird per **Vollvergleich** geprüft, nicht auf Vorkommen: „Als Gast bestellen" muss geklickt werden, ein blosses „Bestellen" nicht. Dass damit auch ein harmloses „Bestätigen" blockiert wird, ist beabsichtigt und kostet bei manchen Shops ein Signal.

### 2. Nie auf eine Dauer warten, immer auf eine Bedingung

`collect/waiting.py` ist der Ersatz für jedes `asyncio.sleep()`. Der Vorgänger hatte 57 Sekunden fest verdrahtete Wartezeit über 33 Stellen. Ein `sleep(3.0)` ist gleichzeitig zu lang für schnelle und zu kurz für langsame Shops — also nicht nur langsam, sondern unzuverlässig.

Wer ein neues `asyncio.sleep()` mit konstanter Zahl einführt, muss begründen, auf welche Bedingung sich nicht warten lässt.

### 3. Confidence wird nie addiert

Noisy-OR mit Dämpfung in `core/scoring.py`. Addition würde aus fünf schwachen Indizien (5 × 20) scheinbare Gewissheit machen. Wächter: `test_scoring.py::test_viele_schwache_signale_erzeugen_keine_scheinsicherheit`.

### 4. Rolle vor Anbieter

`Role.GATEWAY` (wickelt ab) ≠ `Role.WALLET` (PayPal-Button) ≠ `Role.METHOD` (Klarna). Ein PayPal-Button sagt nichts darüber aus, wer die Kartenzahlung abwickelt. Sonderfall `supersedes`: Shopify Payments verdrängt Stripe, weil Stripe dort nur der Unterbau ist.

### 5. Das Tool behauptet nie, weiter gekommen zu sein, als es kam

`checkout_reached` stammt aus dem `CheckoutOutcome`, **nicht** daraus, ob eine Observation die Stufe CHECKOUT trägt — die wird auch beim Scheitern angelegt. Im Vorgänger meldete das Tool deshalb „Checkout erreicht ✓" für Shops, bei denen nicht einmal das Produkt im Warenkorb landete, samt der Warnung „Signatur fehlt vermutlich". Wer dem gefolgt wäre, hätte die Signatur-Datenbank erweitert, während der Adapter kaputt war.

Wächter: `test_checkout_honesty.py`.

### 6. Jedes Ergebnis trägt seine Trichterstufe und seine Belegart

Zwei Felder, zwei verschiedene Aussagen:

- **`tier`** — `statisch`, `gerendert` oder `checkout`. Wie tief gescannt wurde.
- **`acquirer_source`** — `beobachtet`, `angegeben`, `vermutet` oder `keine`. Woher die Aussage über den Abwickler stammt. Dazu `acquirer_note` mit einem Satz Begründung.

Beides sind `computed_field`, nicht `@property` — sonst fehlen sie im JSON und die Oberfläche kann sie nicht anzeigen. Dieser Fehler ist in diesem Projekt schon einmal passiert (`confidence_label`).

Zwei Ergebnisse mit 92 % sind nicht gleichwertig, wenn eines ein beobachteter Request an die Zahlungs-API ist und eines ein Satz auf der Seite „Lieferung und Zahlung". `angegeben` ist belastbar, aber es ist eine Aussage des Händlers, keine Messung.

Bei `keine` unterscheidet `acquirer_note` **warum**: leerer Warenkorb → Selektoren des Adapters; erreichter Checkout ohne Treffer → fehlende Signatur. Wer das verwechselt, erweitert die Signaturdatenbank, während der Adapter kaputt ist — genau der Fehler des Vorgängers. Wächter: `test_ergebnis_darstellung.py`.

### 7. Textgrenzen greifen am Text, nie am HTML

`core/observation.py::strip_tags` entfernt zuerst Tags und begrenzt **danach**. Die umgekehrte Reihenfolge war ein schwerer Fehler: Bei bergfreunde.de hat die Zahlungsseite 873.504 Zeichen HTML, die ersten 200.000 davon fast nur Skripte. Nach dem Entstrippen blieben **103 Zeichen** — der Satz mit dem Anbieternamen lag weit dahinter. Das Tool meldete „kein Zahlungsdienstleister erkannt", während die Antwort im Quelltext stand.

Text macht nur wenige Prozent des HTML aus. Eine HTML-Grenze verwirft deshalb fast den gesamten sichtbaren Inhalt, und zwar bei **jedem** grossen Shop. Wächter: `test_text_extraction.py`.

### 8. `payment_page_text` ist der wichtigste Signaltyp im DACH-Raum

Derselbe Anbietername wiegt sehr unterschiedlich, je nachdem wo er steht. In einem Blogartikel ist „Stripe" Zufall (`dom_text`, ≤ 25). Auf der Seite „Lieferung und Zahlung" ist es eine Aussage des Händlers über seine eigene Abwicklung — oft eine, zu der er verpflichtet ist (`payment_page_text`, ~72).

Das Gewicht ist nur zu verantworten, weil `collect/static.py::looks_like_payment_page` **zwei** Bedingungen prüft: Pfad *und* Textmarken. Shops, die für unbekannte Pfade eine 200er-Startseite liefern, würden sonst als Zahlungsseite gelten.

Belegter Nutzen: bergfreunde.de wird darüber zu 92 % als Unzer erkannt, in 12 Sekunden ohne Browser — obwohl die Checkout-Simulation dort weiterhin scheitert. Zwei unabhängige Wege zum Ergebnis sind der Kern von Zuverlässigkeit.

## Tempo: drei Kategorien, streng getrennt

**Der Trichter ist standardmässig AUS.** Bewusste Umkehr gegenüber dem ersten Entwurf: Er verlässt sich auf Schwellwerte, die noch nicht gegen ein belastbares Golden-Set kalibriert sind. Jeder frühe Ausstieg wäre also auf Verdacht — und ein schnelles falsches Ergebnis ist schlechter als ein langsames richtiges. Standard ist volle Tiefe.

| Kategorie | Beispiele | Bedingung |
|---|---|---|
| **kostenlos** | Warten auf Bedingungen, geteilter Browser, Stufe 1 parallel, Tracking-Hosts abbrechen | Jederzeit zulässig. Ändert nur *wann* geprüft wird, nicht *was* |
| **kalibriert** | Trichter-Schwellwerte, früher Ausstieg | Nur mit Nachweis gegen das Golden-Set |
| **verworfen** | CSS blockieren, Checkout generell weglassen, Timeouts pauschal kürzen | Nicht machen. Begründung in `docs/DESIGN.md` |

Die Schwellwerte stehen ausschliesslich in `config.py` (`skip_render_threshold`, `skip_checkout_threshold`). Das ist der einzige Ort im Projekt, an dem Tempo gegen Genauigkeit getauscht wird.

## Befehle

```bash
.venv/bin/pytest -q                          # Tests, offline
.venv/bin/ruff check src/ tests/ --fix
.venv/bin/mypy src/
.venv/bin/psp-radar signatures --check
.venv/bin/psp-radar scan <url> -v --evidence
.venv/bin/psp-radar scan <url> --statisch    # wenige Sekunden, ohne Browser
.venv/bin/psp-radar batch shops.csv -o out.csv -c 6
.venv/bin/psp-radar serve                    # Oberfläche
.venv/bin/psp-radar eval                     # Erkennungsgüte
```

Umgebung: `uv` mit Python 3.12. **Wichtig:** `VIRTUAL_ENV` vor `uv pip install` unsetzen, sonst landet die Installation in einer fremden venv.

## Teilbarkeit

- **Codespaces** — `.devcontainer/` richtet alles ein, Port 8765 öffnet sich automatisch. Kollegen klicken im Repo auf Code → Codespaces → Create, ohne Installation
- **Docker** — `Dockerfile` auf Basis des offiziellen Playwright-Images, für späteres Hosting
- **Zugangscode** — `PSP_RADAR_ACCESS_CODE`. Leer im Codespace (Port ist dort privat), Pflicht bei öffentlicher Erreichbarkeit

## Wo Fehler entstehen

- **Beinahe-Treffer bei Hosts** — `evilapi.stripe.com` darf nicht als `api.stripe.com` gelten
- **Zu gierige Signaturen** — ein Blogartikel über Stripe darf keinen Treffer erzeugen, deshalb wiegen `dom_text`-Signale ≤ 25. Ausnahme in Planung: `payment_page_text` für Zahlungsinformationsseiten, wo ein Anbietername belastbar ist
- **Adapter brechen still** — häufen sich `checkout_add_to_cart_failed`, liegt es an Selektoren, nicht an Signaturen. Erst `--headed` zusehen, dann anpassen. Shop-eigene Test-Anker (`data-codecept`, `data-testid`) sind stabiler als CSS-Klassen
- **Warenkorb ohne Erfolgskontrolle** — `waiting.read_cart_count` prüft, ob der Klick etwas bewirkt hat. Ohne diese Prüfung läuft die Simulation ins Leere weiter

## Fairness gegenüber den Shops

Rate-Limit **pro Domain** (`batch/funnel.py::DomainLimiter`), nicht global. Vierzig Shops parallel sind unproblematisch; vierzig parallele Zugriffe auf einen Shop nicht. `robots.txt` respektiert, identifizierbarer User-Agent, keine Bestellung, keine Zahlungsdaten, keine Konten, keine Umgehung von Zugangsbeschränkungen.
