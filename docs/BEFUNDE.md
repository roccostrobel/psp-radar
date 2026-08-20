# Befunde aus der manuellen Verifikation

Stand 19.08.2026. Grundlage: acht DACH-Shops, deren Zahlungsseiten gelesen wurden, plus ein vollständiger Checkout-Durchlauf im Browser bis zur Zahlungsauswahl.

Dieses Dokument hält fest, **was das Tool leisten kann und was nicht** — nicht als Absichtserklärung, sondern als Ergebnis von Nachprüfung.

---

## Der wichtigste Befund

**Der Acquirer wird bei vielen Shops erst nach der Zahlungsauswahl geladen — also hinter der Grenze, die wir aus gutem Grund nicht überschreiten.**

Belegt an thomann.de: Warenkorb, Gast-Checkout, Adresse, Versandart, Zahlungsauswahl — alles erreicht. Nach Auswahl von „Kreditkarte" liefen exakt vier fremde Hosts: drei von Amazon Pay und der Google Tag Manager. Kein Karten-Acquirer. Das Kartenformular erscheint erst im Schritt „Übersicht", der letzten Seite vor dem Bestellknopf.

Das ist **keine Fehlfunktion**, sondern eine Grenze des Verfahrens. Wer sie verschieben will, müsste bis auf die Seite mit dem Kaufbutton gehen. Das ist ausgeschlossen (siehe `VERIFIKATION.md`).

---

## Was zuverlässig funktioniert

| Was | Beleg |
|---|---|
| **Shop-System** | 8 von 8 Shops korrekt und mit hoher Confidence. OXID 97 %, Shopify 100 % |
| **Zahlungsarten** | Vollständig ablesbar, sowohl aus der Zahlungsseite als auch aus der Zahlungsauswahl. Bei thomann: Nachnahme, Vorkasse, PayPal, Klarna (Sofort und Ratenzahlung), Kreditkarte, Amazon Pay |
| **Acquirer, wenn im Text genannt** | bergfreunde.de → Unzer, 92 %, in 12 Sekunden ohne Browser |
| **Acquirer, wenn früh geladen** | snocks.com und waterdrop.de → Shopify Payments 98 % über beobachteten Checkout-Traffic |

## Was nicht zuverlässig funktioniert

| Was | Grund |
|---|---|
| **Acquirer bei Shops mit spätem Laden** | Er erscheint erst nach der Zahlungsauswahl. Nicht erreichbar, ohne die Sicherheitsgrenze zu verletzen |
| **Checkout-Simulation allgemein** | bergfreunde.de: Warenkorb-Klick wirkt nicht (Varianten als Kachel-Links in einem angepassten Frontend). snocks.com: über die Kommandozeile erfolgreich, im selben Durchlauf über die Oberfläche nicht — vermutlich Ressourcenkonkurrenz zweier Chromium-Instanzen |
| **Pfade raten** | Von acht Shops fand die Pfadliste **einen**. thomann.de führt seine Seite unter `helpdesk_paymentmethods.html`, bergfreunde unter `/lieferung-und-zahlung/`. Behoben durch Link-Suche im gerenderten Footer, aber bei JavaScript-Footern braucht das einen Browser |

---

## Der CSP-Weg: geprüft und widerlegt

Die Vermutung war, Shops müssten die PSP-Domain in `frame-src` oder `connect-src` whitelisten, **bevor** das Formular lädt — der Header wäre dann eine sichere, schnelle Abkürzung. Diese Behauptung stand mehrfach im Projekt, unter anderem als „praktisch ein Geständnis" im README.

**Messung über 15 DACH-Shops, 19.08.2026** (`scripts/pruefe_csp.py`), geprüft wurden Startseite, Warenkorb und Checkout-Pfade je Shop:

| Quelle | Treffer | Anteil |
|---|---|---|
| CSP-Header überhaupt gesetzt | 1 von 15 | 7 % |
| **Gateway aus CSP ableitbar** | **0 von 15** | **0 %** |
| Gateway aus `preconnect` / `dns-prefetch` | 3 von 15 | 20 % |
| Gateway aus Zahlungsseitentext | 1 von 15 | 7 % |
| **Kombination aller drei** | **4 von 15** | **27 %** |

Geprüfte Shops: bergfreunde, thomann, notebooksbilliger, reichelt, hessnatur, avocadostore, snocks, waterdrop, tchibo, bike24, mueller, bergzeit, globetrotter, fahrrad.de, baur.

**Die Hypothese ist damit erledigt.** Deutsche Shops setzen überwiegend gar keine Content-Security-Policy — der einzige Shop mit CSP (thomann) whitelistet darin keinen Zahlungsanbieter. Die 86 Gateway-Hostmuster der Signaturdatenbank hatten nichts zu greifen.

Die drei Treffer aus Verbindungshinweisen sind ausnahmslos Shopify-Shops, wo der Hinweis auf `shop.app` zeigt. Das ist ein Plattform-Artefakt, keine allgemeine Methode.

### Was daraus folgt

Ohne den echten Zahlungsschritt im Checkout ist der Acquirer bei etwa **einem Viertel** der deutschen Shops bestimmbar. Genau dieser Schritt ist aber

- teuer (Minuten pro Shop),
- unzuverlässig (Adapter scheitern an angepassten Frontends),
- und bei vielen Shops erst hinter der Sicherheitsgrenze sichtbar.

Das ist die ehrliche Antwort auf die Kernfrage des Projekts. Sie war nicht zu erahnen, sondern musste gemessen werden — und sie wäre früher zu haben gewesen, wenn die CSP-Behauptung beim ersten Aufschreiben geprüft worden wäre statt drei Dokumente lang wiederholt.

### Verbleibende Wege

1. **Öffentliche Quellen.** Referenzmeldungen der PSPs, Fallstudien, Presseinformationen. Kein technischer Beleg, für ein Golden-Set aber brauchbar, wenn als solcher gekennzeichnet.
2. **Checkout robuster machen.** Der Weg bleibt der einzige belastbare. Er braucht bessere Adapter, keine neuen Signalquellen.
3. **Anspruch anpassen.** Das Tool als „Shop-System und Zahlungsarten" führen und den Acquirer als Zusatz ausweisen, der in etwa einem Viertel der Fälle mitkommt.

---

## Ehrliche Einschätzung des Reifegrads

Als **Shop-System- und Zahlungsarten-Erkennung** ist das Tool brauchbar: schnell, belegt, nachvollziehbar.

Als **Acquirer-Erkennung** — die ursprüngliche Kernfrage — funktioniert es in zwei von acht geprüften Fällen belastbar, in einem weiteren über einen Textfund. Für die übrigen liefert es ehrlich „nicht ermittelt", was besser ist als ein geratener Treffer, aber die Frage nicht beantwortet.

**Recall auf die Kernfrage: geschätzt 30 bis 40 Prozent.** Diese Zahl ist nicht sauber gemessen, weil das Golden-Set dafür zu klein ist — aber sie ist deutlich näher an der Wirklichkeit als jede Zahl, die vorher in diesem Projekt genannt wurde.

---

## Was daraus gemacht wurde, 20.08.2026

Entschieden wurde Weg 3 als Sofortmassnahme und Weg 2 als Projekt. Weg 1 (öffentliche Quellen) bleibt offen.

### Der Anspruch ist angepasst, nicht die Zahlen

Das Werkzeug führt jetzt **Shop-System und Zahlungsarten** als Hauptergebnis und den Abwickler als zweite, ausdrücklich schwierigere Frage. In Oberfläche, Terminal und CSV.

Neu ist, dass jedes Ergebnis seine **Belegart** trägt (`acquirer_source`), nicht nur eine Prozentzahl:

| Belegart | Bedeutung | Beispiel |
|---|---|---|
| `beobachtet` | im Checkout beim Laden gesehen | snocks.com → Shopify Payments 98 % |
| `angegeben` | der Händler nennt ihn auf seiner Zahlungsseite | bergfreunde.de → Unzer 92 %, 8 s ohne Browser |
| `vermutet` | nur Hosts, Assets, Verbindungshinweise | — |
| `keine` | nichts gefunden, mit Begründung | — |

Der Grund für die Trennung: Alle drei können 92 % ergeben, und sie sind trotzdem nicht dasselbe. `angegeben` ist belastbar — der Händler sagt es über sich selbst, oft weil er dazu verpflichtet ist —, aber es ist keine Messung des Datenverkehrs.

Bei `keine` benennt `acquirer_note` **warum**, und das ist der Teil mit dem grössten praktischen Wert: leerer Warenkorb → Selektoren des Adapters; erreichter Checkout ohne Treffer → fehlende Signatur. Wer das verwechselt, erweitert die Signaturdatenbank, während der Adapter kaputt ist. Genau das hat der Vorgänger getan.

### Zusätzlich: die Anzeige unterscheidet jetzt drei Stufen

`checkout_reached` und `payment_selection_reached` sind getrennt. Vorher meldete der Bericht „Checkout erreicht ✓" direkt neben der Warnung „Zahlungsauswahl nicht erreicht" — beides richtig, zusammen widersprüchlich. Bei snocks.com fällt genau das auseinander.

### Vier Sicherheitsschranken statt einer

Vor den Änderungen am Checkout wurden die Sperren gehärtet. Dabei kamen drei Löcher zum Vorschein, alle mit derselben Form: **Die Dokumentation beschrieb einen Schutz, den der Code nicht hatte.**

1. **Klick ohne Beschriftung.** `safe_click` fügte Text, `value`, `aria-label` und `title` zu einer Zeichenkette zusammen und prüfte diese. Waren alle vier leer, war sie leer — und eine leere Zeichenkette löst keine Sperre aus. Ein Kaufbutton, der nur ein Icon zeigt, wäre geklickt worden. CLAUDE.md behauptete seit dem ersten Tag das Gegenteil.
2. **Dieselbe Beschriftung zweimal.** Text „Bestellen" plus `aria-label="Bestellen"` ergab „Bestellen Bestellen". Steht in keiner Sperrliste.
3. **Drei Klicks an `safe_click` vorbei** — `base.py`, `shopware.py`, `render.py`. In der Praxis harmlos, aber alle drei mit breiten Selektoren wie `fieldset label:not([class*='disabled'])`.

Der neue Wächter dagegen ist eine AST-Prüfung: kein `.click()` ausserhalb von `safe_click`, kein `.fill()` ausserhalb von `safe_fill`, auch nicht in eingebettetem JavaScript. Sie ist die einzige der vier Schranken, die auch das abdeckt, woran niemand gedacht hat.

Dazu neu: `safe_fill` (keine Karten-, IBAN-, CVC- oder Passwortfelder, auch nicht mit Testdaten) und `safe_goto` (keine Bestellabschluss-Pfade, auch nicht per GET). `FORBIDDEN_SUBMIT_PATTERNS` um 16 Muster erweitert, jedes eine gefundene Lücke — „Kauf abschliessen" enthält kein „kaufen", „Jetzt zahlen" war nicht abgedeckt, „Bestellung bestätigen" auch nicht.

### Was das an Erkennung gebracht hat

Nebeneffekt der Härtung, nicht ihr Ziel: Die fest verdrahteten Wartezeiten in Checkout und Rendering sind durch Bedingungen ersetzt (Regel 2, im Checkout bis dahin nicht umgesetzt). snocks.com lief in **108 s statt 116,7 s** und erreichte die Checkout-Seite zuverlässig. Der Verdacht, dass die Flackerhaftigkeit unter Last an den festen Wartezeiten lag, ist damit gestützt, aber nicht bewiesen — dafür braucht es mehrere Läufe.

Ausserdem prüft `add_to_cart` jetzt, ob der Warenkorb tatsächlich gewachsen ist, und `checkout.py` wertet den Rückgabewert von `go_to_cart` aus statt ihn zu verwerfen. Neue Warnung `checkout_cart_empty`, die klar auf die Selektoren zeigt.

### bergfreunde.de: Warenkorb funktioniert, drei geratene Selektoren waren schuld

Der Fall galt seit Tagen als „Kachel-Varianten, schwierig". Nachgelesen im ausgelieferten Markup — ein einzelner GET, kein Klick — zeigten sich **drei** Fehler auf einmal:

| Was der Adapter tat | Was tatsächlich dort steht |
|---|---|
| `.variants a` geklickt | Die `<a>` in `.variants` sind **Bildlinks** auf `bfgcdn.com`. Der Adapter klickte Produktfotos |
| nach dem ersten Treffer aufgehört | Es gibt **zwei** Pflichtdimensionen: `js-var-dimension-color` und `js-var-dimension-size` |
| Rückfall auf `form select` | Die einzigen zwei `<select>` der Seite sind `streamfilter[sort]` und `streamfilter[type]` — eine Option darin lädt die Seite neu, und die Produktseite ist weg |

Die richtige Kachel ist `li[data-varsel="Black"]`. Shop-eigenes Attribut, trägt die Bezeichnung, überlebt einen Designumbau — im Gegensatz zu Tailwind-Klassen, von denen das Frontend nur noch generierte hat.

Ergebnis nach der Korrektur: **Zahlungsauswahl erreicht, `static.unzer.com` im Checkout beobachtet, Unzer zu 99 %** — dieselbe Antwort wie aus dem Text der Zahlungsseite, auf einem unabhängigen Weg. In 93,6 s.

Die Lehre ist dieselbe wie beim CSP-Header: Die Selektoren waren plausibel und nie gegen die Wirklichkeit gehalten. Zehn Minuten Markup lesen hätten Tage gespart.

### Das Golden-Set misst jetzt überhaupt etwas

`psp-radar eval` meldete „Shops im Set: 0", obwohl drei Einträge im Golden-Set stehen. Ursache: Einträge ohne eingefrorene Aufzeichnung wurden **stumm** übersprungen. Wer die Ausgabe las, hielt die Erkennung für nutzlos und die Messung für erledigt.

Zwei Korrekturen:

- Übersprungene Einträge stehen jetzt im Bericht, mit Hinweis, wie man sie aufzeichnet. Bei null gemessenen Shops sagt die Ausgabe ausdrücklich, dass 0,0 % „nichts gerechnet" heisst und nicht „nichts gefunden".
- `psp-radar eval --live --aufzeichnen` friert die Aufzeichnungen ein. Damit liegen zu allen drei Einträgen Fixtures vor.

**Messung, 20.08.2026: Recall 100 %, Precision 100 %, Shop-System 100 % — bei drei Shops, davon zwei Shopify.** Diese Zahlen sind kein erreichtes Ziel, sondern ein Regressionsschutz. Ein Set aus drei Einträgen kann keine 90 % belegen. Wer die 100 % als Erkennungsgüte zitiert, wiederholt genau den Fehler, den dieses Dokument oben beschreibt.

Nebenbei gemessen: Der Offline-Lauf braucht **19 s pro Shop** reine Rechenzeit. README und CLAUDE.md behaupteten „in Sekunden". Ein doppelter Durchgang über die gesamte Signaturdatenbank ist entfernt (2 min → 58 s bei drei Shops), der Rest sind `html_regex`-Signale über mehrere Megabyte Quelltext und ist noch offen. Fixtures liegen gepackt: 28 MB → 4,3 MB.

### Was offen bleibt

- **Golden-Set:** drei Einträge, zwei davon Shopify. Das Ausbauziel von 30 Einträgen über verschiedene Shopsysteme und Anbieter steht unverändert. Bis dahin bleibt der Recall eine Schätzung und der Trichter aus gutem Grund abgeschaltet.
- **Laufzeit der Messung:** 19 s pro Shop offline. Bei 30 Shops zehn Minuten, zu viel für jeden Commit. Braucht Messung, welche Signaltypen die Zeit kosten — nicht Raten.
- **Weg 1:** öffentliche Quellen als Golden-Set-Grundlage, gekennzeichnet als nicht-technischer Beleg.
- **Andere Shopsysteme:** Die Korrektur an bergfreunde betraf OXID. Shopware, WooCommerce und JTL sind nicht gegen echtes Markup geprüft, ihre Selektoren sind also weiterhin geraten. Das ist der nächste konkrete Schritt und derselbe Handgriff: Markup lesen, dann anpassen.
