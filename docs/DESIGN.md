# psp-radar — Entwurf für die zweite Version

Nachfolger von `psp-detector`. Gleiche Erkennungslogik, zwei neue Anforderungen:

1. **Teilbar ohne Installation** — interner Nutzen, Zugang per Link
2. **Schneller** — Listen von Shop-URLs abarbeiten, ohne dass die Qualität leidet

`psp-detector` bleibt unangetastet als Referenz liegen. Alles, was dort belegt funktioniert, wird übernommen; die Signatur-Datenbank und die Sicherheitslogik wandern unverändert mit.

---

## 1. Wo die Zeit tatsächlich hingeht

Gemessen, nicht geschätzt. Drei echte Scans von heute:

| Shop | Modus | Dauer |
|---|---|---|
| snocks.com | voll | 193 s |
| waterdrop.de | voll | 197 s |
| bergfreunde.de | voll | 186 s |
| snocks.com | ohne Checkout | 79 s |
| waterdrop.de | ohne Checkout | 55 s |

Und der entscheidende Befund aus dem Quelltext:

```
57 Sekunden fest verdrahtetes asyncio.sleep() über 33 Stellen
```

Davon laufen pro Scan rund 25–35 Sekunden wirklich ab. Das Tool wartet dort **auf die Uhr, nicht auf ein Ergebnis**. Ein `await asyncio.sleep(3.0)` nach dem Klick auf „Zur Kasse" ist gleichzeitig zu lang für schnelle Shops und zu kurz für langsame — es ist also nicht nur langsam, sondern auch unzuverlässig.

Grobe Aufteilung eines vollen Scans:

| Phase | Anteil | davon Warten |
|---|---|---|
| Stufe 1 statisch (11 Seiten, sequenziell) | 25–40 s | ~10 s |
| Stufe 2 Rendering (Browserstart, 2 Seiten) | 40–60 s | ~8 s |
| Stufe 3 Checkout (5–7 Schritte) | 90–120 s | ~15 s |

---

## 2. Geschwindigkeit: drei Kategorien, streng getrennt

Deine Vorgabe war klar — Tempo nur, wenn die Qualität nicht leidet. Deshalb trenne ich sauber, statt alles in einen Topf zu werfen.

### A — Kostenlos: schneller *und* zuverlässiger

Diese Änderungen verbessern beides. Kein Abwägen nötig.

| Maßnahme | Ersparnis | Warum es die Qualität *hebt* |
|---|---|---|
| **Feste Wartezeiten → Bedingungen** | 25–35 s | Auf das konkrete Ereignis warten (`wait_for_response`, Warenkorbzähler ändert sich, PSP-Iframe erscheint) statt auf Sekunden. Schnelle Shops sind sofort fertig, langsame bekommen bis zur Obergrenze so lange wie sie brauchen — statt nach 3 s abgeschnitten zu werden |
| **Browser wiederverwenden** | 2–3 s pro Shop | Ein Chromium, pro Shop ein eigener Kontext. Isolation bleibt vollständig erhalten, nur der Prozessstart fällt weg. Bei 500 Shops sind das 500 gesparte Browserstarts |
| **Stufe 1 parallelisieren** | 10–20 s | Impressum, AGB, Zahlungsarten und well-known-Pfade parallel statt hintereinander. Mit Semaphore 3 pro Domain bleibt es höflich |
| **Erfolgskontrolle statt Blindklick** | — | Nach „In den Warenkorb" prüfen, ob der Warenkorb wirklich gefüllt ist. Spart das Weiterlaufen aussichtsloser Versuche und behebt gleichzeitig die stille Fehlerquelle von heute |
| **Tracking-Hosts abbrechen** | 3–8 s | Der Request wird protokolliert (Erkennung unberührt), aber nicht heruntergeladen. Zahlungsbezogene Hosts sind ausgenommen, weil deren Skripte Folgerequests auslösen müssen |

**Erwartung: voller Scan von ~190 s auf 80–110 s — ohne jede Einbuße.**

### B — Kalibriert: Tempo gegen Tiefe, aber messbar

Hier wird tatsächlich abgewogen. Zulässig nur, wenn der Schwellwert **gegen das Golden-Set geprüft** ist.

**Der Trichter.** Für Listen die wichtigste Änderung überhaupt:

```
Durchgang 1   alle URLs      ohne Browser, 20 parallel      2–4 s/Shop
              ↓ nur Shops unter dem Schwellwert
Durchgang 2   Rendering      geteilter Browser, 8 parallel  15–25 s/Shop
              ↓ nur Shops, die weiterhin unklar sind
Durchgang 3   Checkout       3–4 parallel                   40–70 s/Shop
```

Der Punkt: Ein Shop, dessen CSP-Header `frame-src https://*.adyen.com` enthält, braucht keine Checkout-Simulation. Das Ergebnis wäre dasselbe, nur 180 Sekunden später.

Jedes Ergebnis trägt sichtbar, **aus welchem Durchgang** es stammt. Wer „nur statisch erkannt" liest, kann selbst entscheiden, ob ihm das genügt.

**Neue Erkenntnis von heute, die hier hineinspielt:** Bei bergfreunde.de stand der Zahlungsdienstleister im Klartext auf der Seite „Lieferung und Zahlung" — *„Der Zahlungsprozess wird über unseren Dienstleister Payolution/Unzer abgewickelt."* Diese Seite kostet 2 Sekunden. Im DACH-Raum zwingen Informationspflichten die Shops zu solchen Angaben, das ist kein Zufallsfund.

Bisher wiegen Textsignale generell ≤ 25, um Fehlalarme durch Blogartikel zu verhindern. Aber ein Anbietername **auf der Zahlungsinformationsseite** ist etwas völlig anderes als derselbe Name in einem Artikel. Deshalb: neuer Signaltyp `payment_page_text` mit Gewicht ~70, der nur auf diesen Seiten greift. Das ist gleichzeitig schneller *und* genauer — die interessanteste Einzelmaßnahme des Entwurfs.

### C — Verworfen: würde die Qualität kosten

Zur Transparenz, was ich **nicht** mache:

- **CSS blockieren** — bricht Playwrights Sichtbarkeitsprüfung, von der jeder Adapter abhängt
- **Checkout generell weglassen** — genau der Kern des Tools
- **Nur die Startseite ansehen** — heute empirisch widerlegt
- **Parallelität pro Domain hochziehen** — unhöflich gegenüber den Shops und ein Weg auf Sperrlisten
- **Timeouts pauschal kürzen** — bevorzugt schnelle Shops und verfälscht die Statistik systematisch

---

## 3. Der Haken, den ich zuerst ansprechen muss

> „Änderungen, die sich auf die Schnelligkeit auswirken, nur wenn die Qualität nicht darunter leidet."

Diese Bedingung lässt sich derzeit **nicht überprüfen**. Das Golden-Set hat einen einzigen belastbaren Eintrag (bergfreunde.de, heute verifiziert), Fixtures existieren keine. Ohne Messgrundlage ist jede Aussage über erhaltene Qualität ein Gefühl.

Deshalb: **Meilenstein 1 ist die Messbarkeit, nicht das Tempo.** Erst 25–30 verifizierte Shops mit eingefrorenen Fixtures, dann eine Referenzmessung, dann optimieren — und nach jeder Änderung nachrechnen. Das klingt nach Umweg und ist der kürzeste Weg zu einer Aussage, auf die man sich verlassen kann.

Umgekehrt gilt: Kategorie A kann vorher laufen, weil dort nichts abgewogen wird.

---

## 4. Architektur für die Teilbarkeit

Das Kernproblem: Ein Chromium-Browser lässt sich nicht in einem Browser-Tab ausführen. Ein reines Frontend ist deshalb unmöglich — irgendwo muss ein Server rechnen.

Konsequenz für den Aufbau: **Erkennung strikt von Transport trennen**, damit derselbe Kern als CLI, lokale UI, gehosteter Dienst oder Worker läuft, ohne umgebaut zu werden.

```
psp-radar/
├── core/         Erkennung. Kein Netzwerk, kein Browser.
│                 Observation → Evidenz → Detection. Vollständig offline testbar.
├── collect/      Beschaffung. httpx-Sammler + Playwright-Sammler + Adapter.
├── batch/        Trichter, Worker-Pool, Warteschlange, Cache
├── api/          FastAPI: Jobs, Fortschritt, Ergebnisse, CSV-Export
└── web/          Statisches Frontend, redet nur mit der API
```

`core` bleibt frei von Abhängigkeiten zu allem anderen. Das ist der Grund, warum das alte Projekt offline testbar war, und der Grund, warum diese Trennung diesmal noch strenger wird.

### Verteilung

Empfehlung: **Frontend statisch auf GitHub Pages, Rechenteil auf einem kleinen Server.**

Der Link, den du weitergibst, zeigt auf GitHub Pages — kostenlos, sofort erreichbar, kein Konto, kein Download. Die Seite ruft im Hintergrund die API auf. Wer den Link öffnet, merkt von der Zweiteilung nichts.

Was das braucht:

- Kleiner Server, ~4 GB RAM (Chromium ist der Speicherfresser). Größenordnung 5–15 € im Monat
- **Zugangscode**, weil ein offener Scanner, der fremde Checkouts durchklickt, gefunden und missbraucht wird. Für internen Gebrauch reicht ein gemeinsames Kennwort plus Rate-Limit pro Nutzer
- Docker-Image, damit dasselbe Artefakt später unverändert auf eure Plattform wandert

Zwischenlösung, falls der Server dauert: **GitHub Codespaces**. Kollegen starten das Projekt per Klick aus dem Repo, ohne Installation. Kein dauerhafter Link, aber sofort verfügbar und kostenlos.

---

## 5. Etappen

| # | Inhalt | Ergebnis |
|---|---|---|
| **M1** | Repo, Kern portiert, `core`/`collect` getrennt, Fixture-Recorder | Läuft, offline testbar |
| **M2** | **Golden-Set auf 25–30 verifizierte Shops, Fixtures, Referenzmessung** | Qualität wird messbar |
| **M3** | Kategorie A umsetzen, nach jeder Änderung Golden-Set nachrechnen | ~2× schneller, Metrik unverändert |
| **M4** | Trichter, Schwellwert kalibrieren, Batch-Worker, Cache | Listen praktikabel |
| **M5** | API, statisches Frontend, Docker, Zugangscode | Teilbar per Link |
| **M6** | Deployment, Lasttest mit echter Shopliste | Im Betrieb |

Für `/goal` ist M3 der interessante Meilenstein, weil dort ein hartes Kriterium existiert:

```
/goal Alle Tests grün, ruff und mypy sauber, `psp-radar eval` mit Exit-Code 0
(Recall >= 90%, Precision >= 95%) UND die mittlere Scandauer über das
Golden-Set mindestens 40% unter der in docs/BASELINE.md festgehaltenen
Referenz. Verschlechtert eine Änderung Recall oder Precision, nimm sie
zurück statt den Schwellwert zu senken.
```

Der zweite Satz ist der wichtige. Ohne ihn ist die naheliegendste Art, das Ziel zu erreichen, die Messlatte zu senken.

---

## 6. Was ich noch von dir brauche

1. **Wo soll der Rechenteil laufen?** Das ist die blockierende Entscheidung — ohne Server kein Link.
2. **Wie viele URLs** pro Lauf realistisch? 50, 500 oder 5000 entscheidet, ob eine echte Warteschlange und Datenbank nötig sind.
3. **Wer darf zugreifen?** Gemeinsames Kennwort, Firmen-SSO oder IP-Beschränkung.
4. **Repo-Name** — Vorschlag `psp-radar`, damit die Abgrenzung zum Vorgänger klar bleibt.
