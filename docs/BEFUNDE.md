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

## Was der Acquirer-Nachweis stattdessen bräuchte

Drei Wege, die ohne Regelbruch funktionieren könnten — alle ungeprüft:

1. **CSP-Header des Checkouts.** Shops müssen die PSP-Domain in `frame-src` oder `connect-src` whitelisten, **bevor** das Formular lädt. Der Header steht auf der Zahlungsseite bereits zur Verfügung. Das ist der aussichtsreichste unerprobte Ansatz.
2. **Preload- und Preconnect-Hinweise.** Viele Shops kündigen den PSP-Host per `<link rel="preconnect">` an, damit die Verbindung schon steht, wenn das Formular kommt.
3. **Öffentliche Quellen.** Referenzmeldungen der PSPs, Fallstudien, Presseinformationen. Kein technischer Beleg, aber für ein Golden-Set brauchbar, wenn als solcher gekennzeichnet.

---

## Ehrliche Einschätzung des Reifegrads

Als **Shop-System- und Zahlungsarten-Erkennung** ist das Tool brauchbar: schnell, belegt, nachvollziehbar.

Als **Acquirer-Erkennung** — die ursprüngliche Kernfrage — funktioniert es in zwei von acht geprüften Fällen belastbar, in einem weiteren über einen Textfund. Für die übrigen liefert es ehrlich „nicht ermittelt", was besser ist als ein geratener Treffer, aber die Frage nicht beantwortet.

**Recall auf die Kernfrage: geschätzt 30 bis 40 Prozent.** Diese Zahl ist nicht sauber gemessen, weil das Golden-Set dafür zu klein ist — aber sie ist deutlich näher an der Wirklichkeit als jede Zahl, die vorher in diesem Projekt genannt wurde.

Vor jeder weiteren Funktion gehört Weg 1 geprüft: Reicht der CSP-Header des Checkouts aus, um den Acquirer zu bestimmen? Wenn ja, ist das Tool schnell, sicher und zuverlässig zugleich. Wenn nein, ist die Kernfrage mit vertretbarem Aufwand nicht allgemein beantwortbar, und das gehört offen gesagt statt umgangen.
