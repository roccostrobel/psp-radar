# psp-radar

Ermittelt aus Shop-URLs, **welcher Zahlungsdienstleister dahintersteckt** — dazu Zahlungsarten, Shop-System und zu jedem Fund ein Beleg.

Nachfolger von [`psp-detector`](https://github.com/roccostrobel/psp-detector) mit zwei neuen Schwerpunkten: **teilbar ohne Installation** und **schnell genug für Listen**.

---

## Loslegen

Einmalig einrichten:

```bash
git clone https://github.com/roccostrobel/psp-radar.git
cd psp-radar
./einrichten.sh
```

Danach genügt ein **Doppelklick auf `start-lokal.command`**. Der Starter prüft die Umgebung, startet den Server und öffnet die Oberfläche. Fenster offen lassen, solange du das Tool nutzt.

Wenn etwas nicht stimmt, sagt es das vorher:

```bash
.venv/bin/psp-radar doctor
```

### Zu GitHub Codespaces

Die Codespaces-Einrichtung liegt in `.devcontainer/` und wird von der CI geprüft, hat aber **in der Praxis nicht funktioniert** — zwei Anläufe scheiterten an Umgebungsproblemen im Container, die als Erkennungsfehler erschienen. Bis das belastbar gelöst ist, ist der lokale Weg der empfohlene. Details in [`docs/CODESPACES.md`](docs/CODESPACES.md).

---

## Warum das nicht trivial ist

Der Zahlungsdienstleister ist auf der Startseite eines Shops fast immer **unsichtbar**. Er lädt erst im Checkout. Empirisch belegt am selben Shop:

```
snocks.com  ohne Checkout-Simulation  →  PSP nicht ermittelbar
snocks.com  mit Checkout-Simulation   →  Shopify Payments, 98 %
```

Und die naheliegende Abkürzung funktioniert **nicht**. Frühere Fassungen dieses Textes behaupteten, der CSP-Header eines Shops verrate den Anbieter, weil dort jede Checkout-Domain whitelistet sein muss. Gemessen über 15 DACH-Shops: **1 von 15 setzt überhaupt eine CSP, 0 von 15 lassen daraus den Acquirer ableiten.** Die Behauptung war plausibel und ungeprüft.

Was ohne Checkout wirklich trägt, zusammengenommen:

| Quelle | Treffer bei 15 Shops |
|---|---|
| CSP-Header | 0 |
| preconnect / dns-prefetch | 3 (alle Shopify) |
| Anbietername auf der Zahlungsseite | 1 |
| **Kombination** | **4 = 27 %** |

Details und Methodik in [`docs/BEFUNDE.md`](docs/BEFUNDE.md).

Der **Trichter** bleibt trotzdem sinnvoll, nur mit realistischerer Erwartung:

```
Durchgang 1   alle URLs      ohne Browser        2–4 s     hohe Parallelität
              ↓ nur unklare Fälle
Durchgang 2   Rendering      geteilter Browser   15–25 s   mittlere
              ↓ nur weiterhin unklare
Durchgang 3   Checkout       geteilter Browser   40–70 s   niedrige
```

Jedes Ergebnis trägt sichtbar, aus welchem Durchgang es stammt. Zwei Treffer mit 96 % sind nicht gleichwertig, wenn einer aus einem HTTP-Header und einer aus beobachtetem Checkout-Traffic kommt.

---

## Nutzung

```bash
# Einzelabfrage, Trichter (Standard)
psp-radar scan https://beispielshop.de

# Nur statisch — wenige Sekunden, ohne Browser
psp-radar scan https://beispielshop.de --statisch

# Volle Tiefe erzwingen
psp-radar scan https://beispielshop.de --voll --evidence

# Liste abarbeiten
psp-radar batch shops.csv -o ergebnisse.csv -c 6

# Oberfläche
psp-radar serve

# Erkennungsgüte messen
psp-radar eval
```

Die Oberfläche nimmt einzelne URLs und ganze Listen an und exportiert als CSV.

---

## Architektur

```
core/      reine Logik — kein Netzwerk, kein Browser, keine Seiteneffekte
collect/   Beschaffung: httpx, Playwright, Plattform-Adapter
batch/     Trichter, Worker-Pool, Cache
eval/      Golden-Set, Fixtures, Messung
api/       FastAPI mit Zugangscode
web/       Oberfläche
```

`core` importiert nichts aus den anderen Schichten — erzwungen durch `tests/test_architecture.py`. Der Grund ist praktisch: Nur so lässt sich die gesamte Erkennung offline und deterministisch gegen eingefrorene Aufzeichnungen prüfen, in Sekunden und ohne einen einzigen echten Shop anzufassen.

### Confidence: Noisy-OR statt Addition

```
p = 1 − Π(1 − wᵢ · decay^i)
```

Addition würde aus fünf schwachen Indizien (5 × 20) scheinbare Gewissheit machen. Ein einzelner harter Treffer — Live-Key im Quelltext, Request an die Zahlungs-API — reicht allein. Viele weiche Treffer landen ehrlich bei *wahrscheinlich*.

---

## Geschwindigkeit: drei Kategorien

Tempo wird nur dort geholt, wo es nichts kostet — und wo es etwas kostet, wird es gemessen.

| Kategorie | Maßnahmen | Bedingung |
|---|---|---|
| **kostenlos** | Warten auf Bedingungen statt auf Sekunden, geteilter Browser, Stufe 1 parallel | Jederzeit. Verbessert auch die Zuverlässigkeit |
| **kalibriert** | Trichter-Schwellwerte, früher Ausstieg | Nur mit Nachweis gegen das Golden-Set |
| **verworfen** | CSS blockieren, Checkout weglassen, Timeouts kürzen | Nicht gemacht — Begründung in `docs/DESIGN.md` |

Der Vorgänger enthielt **57 Sekunden fest verdrahtete Wartezeit** über 33 Stellen. Ein `sleep(3.0)` nach „Zur Kasse" ist für schnelle Shops Verschwendung und für langsame zu kurz — also nicht nur langsam, sondern unzuverlässig. `collect/waiting.py` wartet stattdessen auf das Ereignis, auf das es ankommt.

Referenzwerte und Zielvorgaben: [`docs/BASELINE.md`](docs/BASELINE.md).

---

## Zuverlässigkeit

Solche Tools scheitern nicht daran, dass sie nicht laufen, sondern daran, dass sie *plausibel falsch* liegen. Drei Tests halten das im Zaum:

- **`test_safety.py`** — es wird nie eine Bestellung ausgelöst. Deckte im Vorgänger eine echte Lücke auf: „Kostenpflichtig bestellen" wäre geklickt worden
- **`test_checkout_honesty.py`** — das Tool behauptet nie, weiter gekommen zu sein, als es kam. Im Vorgänger meldete es „Checkout erreicht ✓" für Shops, bei denen nicht einmal das Produkt im Warenkorb landete
- **`test_architecture.py`** — die Schichtentrennung erodiert nicht durch einen naheliegenden Import

Dazu `unbekannt` mit Begründung statt geratenem Treffer, und eine Deckelung der Confidence, solange der Checkout nicht gesehen wurde.

---

## Fairness gegenüber den Shops

- Rate-Limit **pro Domain**, nicht global. Vierzig Shops parallel sind unproblematisch; vierzig Zugriffe auf einen Shop nicht
- `robots.txt` wird gelesen und respektiert
- Identifizierbarer User-Agent
- **Niemals** eine Bestellung abschliessen, niemals Zahlungsdaten eingeben, niemals Konten anlegen — harter Stopp bei der Zahlungsauswahl
- Keine Speicherung personenbezogener Daten, keine Umgehung von Zugangsbeschränkungen

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
