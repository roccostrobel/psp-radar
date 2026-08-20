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

Vor jeder weiteren Funktion gehört Weg 1 geprüft: Reicht der CSP-Header des Checkouts aus, um den Acquirer zu bestimmen? Wenn ja, ist das Tool schnell, sicher und zuverlässig zugleich. Wenn nein, ist die Kernfrage mit vertretbarem Aufwand nicht allgemein beantwortbar, und das gehört offen gesagt statt umgangen.
