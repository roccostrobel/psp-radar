# Referenzmessung

Die Vergleichsgrundlage für alle Tempoänderungen. Ohne diese Zahlen ist „schneller geworden, ohne Qualitätsverlust" eine Behauptung.

**Regel:** Jede Änderung, die die Laufzeit betrifft, wird gegen diese Tabelle gestellt. Verschlechtern sich Recall oder Precision, wird die Änderung zurückgenommen — nicht der Zielwert gesenkt.

---

## Ausgangslage (Vorgänger psp-detector, 2026-08-14/15)

Gemessen auf einem MacBook, Intel, macOS 14.8, Chromium headless, Wohnanschluss.

| Shop | Modus | Dauer | Ergebnis |
|---|---|---|---|
| snocks.com | voll | 193,2 s | Shopify Payments 98 % |
| waterdrop.de | voll | 197,4 s | Shopify Payments 98 % |
| bergfreunde.de | voll | 186,0 s | PSP nicht ermittelt (Warenkorb fehlgeschlagen) |
| snocks.com | ohne Checkout | 79,4 s | PSP nicht ermittelt |
| waterdrop.de | ohne Checkout | 55,3 s | PSP nicht ermittelt |
| bergfreunde.de | ohne Checkout | 77,2 s | PSP nicht ermittelt |

**Mittelwert voller Scan: 192,2 s.**

### Wo die Zeit lag

| Ursache | Anteil |
|---|---|
| Fest verdrahtetes `asyncio.sleep()` | 57 s im Code über 33 Stellen, davon 25–35 s pro Lauf tatsächlich abgewartet |
| Browserstart pro Shop | 2–3 s |
| Stufe 1 sequenziell über 11 Seiten | 25–40 s |

---

## Zielwerte für psp-radar

| Kennzahl | Ausgangslage | Ziel | Kategorie |
|---|---|---|---|
| Voller Scan, Mittelwert | 192 s | **≤ 110 s** | kostenlos (Warten auf Bedingungen, Browser geteilt, Stufe 1 parallel) |
| Statischer Scan | — | **≤ 6 s** | kostenlos |
| Liste mit 100 Shops, Trichter | — | **≤ 35 min** bei 6 parallel | kalibriert |
| Recall auf dem Golden-Set | *nicht gemessen* | **≥ 90 %** | darf nicht sinken |
| Precision auf dem Golden-Set | *nicht gemessen* | **≥ 95 %** | darf nicht sinken |

---

## Das offene Problem

Recall und Precision stehen als „nicht gemessen" in der Tabelle, und das ist der wichtigste Eintrag darin.

Das Golden-Set enthält aktuell **einen** unabhängig verifizierten Shop: bergfreunde.de, am 15.08.2026 manuell im Browser bis zur Zahlungsauswahl durchlaufen und zusätzlich über die Seite „Lieferung und Zahlung" bestätigt (Payolution/Unzer). Zwei weitere Einträge tragen `verified_via: tool_observed` — sie sind mit dem Tool selbst belegt und messen damit nur, ob das Tool mit sich selbst übereinstimmt.

Solange das so ist, lässt sich die Vorgabe „Tempo nur ohne Qualitätsverlust" **nicht überprüfen**. Deshalb ist Meilenstein 2 die Messbarkeit und nicht das Tempo.

Was fehlt:

- 25–30 verifizierte Shops, gemischt über Shop-Systeme, PSPs, Größenklassen und DE/AT/CH
- Für jeden eine eingefrorene Fixture, damit die Auswertung offline und in Sekunden läuft
- Ein erster echter Lauf von `psp-radar eval`, dessen Ergebnis hier eingetragen wird

Bis dahin gilt: **Änderungen der Kategorie „kostenlos" sind zulässig** (sie ändern nur, *wann* geprüft wird, nicht *was*), Änderungen der Kategorie „kalibriert" nicht.

---

## Wie neu gemessen wird

```bash
# Erkennungsgüte, offline gegen Fixtures
.venv/bin/psp-radar eval

# Laufzeit über das Golden-Set, live
.venv/bin/psp-radar eval --live

# Einzelner Shop mit Zeitangabe
.venv/bin/psp-radar scan https://shop.de -v
```

Messungen bitte **mit Datum und Gerät** ergänzen. Eine Zahl ohne Kontext ist beim nächsten Vergleich wertlos, weil Netzanbindung und Maschine den Wert stärker beeinflussen als die meisten Codeänderungen.
