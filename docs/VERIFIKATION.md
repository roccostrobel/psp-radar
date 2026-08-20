# Regeln für die Verifikation im Browser

Diese Regeln gelten, wenn ein Shop **von Hand** im Browser geprüft wird, um einen Golden-Set-Eintrag zu belegen. Sie sind dieselben, die im Code für die automatische Checkout-Simulation gelten — nur dass hier ein Mensch oder ein Assistent klickt und die Sperren daher nicht technisch erzwungen, sondern eingehalten werden müssen.

Der Grund für die Verschriftlichung: Eine technische Sperre wie `adapters/base.py::safe_click` lässt sich testen. Ein Vorsatz nicht. Also wird er wenigstens nachlesbar.

---

## Absolut ausgeschlossen

Diese Dinge werden **nie** getan, unabhängig davon wie nützlich das Ergebnis wäre:

| Nicht tun | Warum |
|---|---|
| **Bestellung auslösen** | Kostet einen echten Händler Geld und Aufwand. Harter Stopp bei der Zahlungsauswahl, Schritt 3 von 5 |
| Buttons anklicken, die „pflichtig", „kaufen", „jetzt bestellen", „place order", „pay now" enthalten | § 312j Abs. 3 BGB verlangt für deutsche Kaufbuttons eine eindeutige Beschriftung — praktisch jeder enthält „pflichtig". Die vollständige Liste steht in `config.py::FORBIDDEN_SUBMIT_PATTERNS` |
| **Zahlungsdaten eingeben** | Keine Kartennummer, keine IBAN, keine PayPal-Anmeldung, kein Klarna-Login. Auch keine Testdaten in Zahlungsfelder |
| **Kundenkonto anlegen** | Immer Gast-Bestellung. Wo es keine gibt, endet die Prüfung dort |
| Echte personenbezogene Daten verwenden | Keine echten Namen, Adressen, Telefonnummern oder E-Mail-Adressen — auch nicht die eigenen |
| Zugangsbeschränkungen umgehen | Keine Logins Dritter, keine CAPTCHAs lösen, keine Sperren austricksen |
| Gutscheine oder Rabattcodes einlösen | Verändert den Zustand beim Händler |

---

## Erlaubt und wie

| Schritt | Vorgehen |
|---|---|
| Consent-Dialog | **Datensparsame Option wählen** — nur technisch notwendige Cookies. Auch wenn dadurch Skripte fehlen, die man gerne sähe |
| Produkt in den Warenkorb | Ein Artikel, kleinste verfügbare Variante, Menge 1 |
| Gast-Checkout | Nur mit erkennbar synthetischen Daten: `Test Testerson`, `Teststrasse 1`, `10115 Berlin`, `psp-radar-test@example.com` |
| Zahlungsauswahl | Zahlungsart **auswählen** ist erlaubt (löst das Laden des PSP-Skripts aus). Bestätigen nicht |
| Netzwerk mitlesen | Hosts und Header protokollieren |
| **Aufräumen** | Warenkorb leeren, Tab schliessen. Beim Shop bleibt nichts zurück |

---

## Nach jeder Prüfung

1. Warenkorb geleert
2. Tab geschlossen
3. Im Golden-Set eingetragen mit `verified_via`, Datum und dem konkreten Beleg

---

## Rate-Limit

Ein Shop wird in einer Sitzung **einmal** geprüft, nicht mehrfach. Zwischen zwei Shops eine kurze Pause. Wer vierzig Shops hintereinander durchklickt, verhält sich wie ein Angriff, auch mit guten Absichten.

---

## Wenn eine Regel im Weg steht

Dann endet die Prüfung, und der Eintrag bleibt offen. Ein fehlender Golden-Set-Eintrag ist ein bekanntes Loch. Eine ausgelöste Bestellung bei einem fremden Händler ist ein Schaden, der sich nicht zurücknehmen lässt — und ein Eintrag, der durch Regelbruch entstanden ist, macht die ganze Messung fragwürdig.
