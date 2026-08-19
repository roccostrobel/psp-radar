# psp-radar — Projektkontext

Ermittelt aus Shop-URLs den Zahlungsdienstleister, die Zahlungsarten und das Shop-System. Schwerpunkt DACH. Nachfolger von `psp-detector`, das als Referenz unangetastet liegen bleibt.

Zwei Anforderungen unterscheiden dieses Projekt vom Vorgänger:

1. **Teilbar ohne Installation** — interner Nutzen, Zugang per Link oder Codespace
2. **Schnell genug für Listen** — 50 bis 200 Shop-URLs pro Lauf

## Die eine Sache, die man verstanden haben muss

**Der PSP ist auf der Startseite unsichtbar.** Er lädt erst im Checkout. Empirisch belegt: `snocks.com` ohne Checkout-Simulation → Shop-System zu 100 % erkannt, PSP nicht ermittelbar. Mit Simulation → Shopify Payments zu 98 %.

Daraus folgt aber **nicht**, dass jeder Shop den Checkout braucht. Wessen CSP-Header `frame-src https://*.adyen.com` enthält, ist beantwortet. Genau diese Unterscheidung ist der Trichter.

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

## Unverhandelbare Regeln

### 1. Es wird nie eine Bestellung ausgelöst

`collect/adapters/base.py::safe_click` prüft vor **jedem** Klick den Beschriftungstext gegen `FORBIDDEN_SUBMIT_PATTERNS`. Ohne ermittelbaren Text wird nicht geklickt.

Die Muster nutzen, dass § 312j Abs. 3 BGB für deutsche Kaufbuttons eine eindeutige Beschriftung vorschreibt — praktisch jeder enthält „pflichtig". Diese Liste darf **nur erweitert, nie gekürzt** werden. `tests/test_safety.py` ist der wichtigste Testfile im Projekt. Er deckte im Vorgänger eine echte Lücke auf: „Kostenpflichtig bestellen" wäre geklickt worden.

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

### 6. Jedes Ergebnis trägt seine Trichterstufe

Feld `tier`: `statisch`, `gerendert` oder `checkout`. Zwei Ergebnisse mit 96 % sind nicht gleichwertig, wenn eines aus einem CSP-Header und eines aus beobachtetem Checkout-Traffic stammt.

## Tempo: drei Kategorien, streng getrennt

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
