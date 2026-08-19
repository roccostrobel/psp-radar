# Abnahmekriterien

Referenz für `/goal`. Jedes Kriterium ist ein Befehl mit Exit-Code, kein „sieht gut aus".

---

## M1 — Gerüst ✅

| # | Kriterium | Prüfbefehl |
|---|---|---|
| 1.1 | Paket importierbar | `.venv/bin/python -c "import psp_radar"` |
| 1.2 | Signatur-Datenbank valide | `.venv/bin/psp-radar signatures --check` |
| 1.3 | Lint sauber | `.venv/bin/ruff check src/ tests/` |
| 1.4 | Tests grün | `.venv/bin/pytest -q` |
| 1.5 | **Schichtentrennung hält** | `.venv/bin/pytest tests/test_architecture.py` |
| 1.6 | Sicherheitstests grün | `.venv/bin/pytest tests/test_safety.py` |
| 1.7 | Ehrlichkeit beim Checkout | `.venv/bin/pytest tests/test_checkout_honesty.py` |

## M2 — Messbarkeit ⬅ **Ziel für `/goal`, Schritt 1**

Ohne diesen Meilenstein ist jede Tempoaussage unbelegbar.

| # | Kriterium | Zielwert | Prüfbefehl |
|---|---|---|---|
| 2.1 | Golden-Set gefüllt | ≥ 25 Shops, jeder mit `verified_via` ≠ `""` und ≠ `tool_observed` | `pytest tests/test_golden_set.py` |
| 2.2 | Fixtures aufgezeichnet | für jeden Eintrag | `pytest tests/test_golden_set.py::test_fixtures_vollstaendig` |
| 2.3 | Vielfalt | ≥ 5 Shop-Systeme, ≥ 6 verschiedene PSPs | `pytest tests/test_golden_set.py::test_vielfalt` |
| 2.4 | Referenzmessung eingetragen | Recall und Precision in `docs/BASELINE.md` | manuell, danach fest |
| 2.5 | Recall | ≥ 90 % | `.venv/bin/psp-radar eval` |
| 2.6 | Precision | ≥ 95 % | `.venv/bin/psp-radar eval` |

**Hinweis zu 2.1:** `tool_observed` zählt nicht als Verifikation. Ein Golden-Set, das mit dem eigenen Tool belegt ist, misst nur, ob das Tool mit sich selbst übereinstimmt. Zulässige Belegarten: `checkout_manual`, `impressum`, `csp_header`.

## M3 — Tempo, Kategorie „kostenlos" ⬅ **Ziel für `/goal`, Schritt 2**

| # | Kriterium | Zielwert | Prüfbefehl |
|---|---|---|---|
| 3.1 | Keine konstanten `sleep` mehr in `collect/` | 0 Treffer | `! grep -rn 'asyncio.sleep([0-9]' src/psp_radar/collect/` |
| 3.2 | Voller Scan, Mittelwert Golden-Set | ≤ 110 s (von 192 s) | `.venv/bin/psp-radar eval --live` |
| 3.3 | Statischer Scan | ≤ 6 s | `.venv/bin/psp-radar scan <url> --statisch` |
| 3.4 | **Recall und Precision unverändert** | wie M2 | `.venv/bin/psp-radar eval` |

## M4 — Trichter

| # | Kriterium | Zielwert |
|---|---|---|
| 4.1 | Schwellwerte kalibriert, Kosten dokumentiert | `psp-radar eval --calibrate` |
| 4.2 | 100 Shops im Trichter | ≤ 35 min bei 6 parallel |
| 4.3 | Rate-Limit pro Domain greift | `pytest tests/test_funnel.py::test_eine_sitzung_pro_domain` |
| 4.4 | Recall im Trichter höchstens 2 Punkte unter voller Tiefe | `psp-radar eval --compare-modes` |

## M5 — Teilbarkeit

| # | Kriterium | Prüfung |
|---|---|---|
| 5.1 | Codespace startet und Oberfläche erreichbar | manuell, einmal je Änderung an `.devcontainer/` |
| 5.2 | Docker-Image baut und antwortet | `docker build -t psp-radar . && docker run -p 8765:8765 psp-radar` |
| 5.3 | Zugangscode greift | `pytest tests/test_api.py::test_ohne_code_kein_zugriff` |
| 5.4 | CSV-Export funktioniert | `pytest tests/test_api.py::test_csv_export` |

---

## Formulierung für `/goal`

**Schritt 1 — Messbarkeit:**

```
/goal In diesem Projekt gilt M2 aus docs/ACCEPTANCE.md als erreicht:
tests/test_golden_set.py gruen, mindestens 25 Shops im Golden-Set mit
verified_via aus (checkout_manual, impressum, csp_header) - niemals
tool_observed -, fuer jeden eine Fixture unter tests/fixtures/, und
`.venv/bin/psp-radar eval` beendet sich mit Exit-Code 0. Trage die
gemessenen Werte in docs/BASELINE.md ein. Verifiziere jeden Shop
unabhaengig vom eigenen Tool: Impressum und Zahlungsinformationsseite
lesen, CSP-Header pruefen, im Zweifel den Checkout selbst ansehen. Loese
niemals eine Bestellung aus und aendere FORBIDDEN_SUBMIT_PATTERNS nur um
Muster zu ERGAENZEN.
```

**Schritt 2 — Tempo:**

```
/goal In diesem Projekt gilt M3 aus docs/ACCEPTANCE.md als erreicht:
`.venv/bin/pytest -q` gruen, ruff und mypy sauber, kein konstantes
asyncio.sleep mehr unter src/psp_radar/collect/, und die mittlere Scandauer
ueber das Golden-Set liegt bei maximal 110 Sekunden gegenueber den 192
Sekunden aus docs/BASELINE.md. Dabei muessen Recall und Precision aus
docs/BASELINE.md **exakt gehalten oder verbessert** werden. Verschlechtert
eine Aenderung eine der beiden Kennzahlen, nimm die Aenderung zurueck -
senke niemals den Zielwert und passe niemals das Golden-Set an, um die
Messung zu bestehen.
```

Der letzte Satz ist der wichtigste im ganzen Dokument. Ohne ihn ist der bequemste Weg zum Ziel, die Messlatte zu senken — und das Ergebnis wäre ein Tool, das schnell und falsch ist.

---

## Dauerhafte Nebenbedingungen

Gelten für **jede** Änderung:

1. **`FORBIDDEN_SUBMIT_PATTERNS` darf nur wachsen.** Ein Muster zu entfernen ist ein Sicherheitsvorfall.
2. **`test_safety.py`, `test_architecture.py` und `test_checkout_honesty.py` müssen grün sein.** Ohne `skip`, ohne `xfail`.
3. **Confidence wird nicht addiert.**
4. **Golden-Set-Einträge brauchen einen Beleg, der nicht vom eigenen Tool stammt.**
5. **Kein Ergebnis ohne `tier`.** Wer nicht sagt, wie tief er geschaut hat, behauptet mehr als er weiss.
6. **Rate-Limit pro Domain bleibt.** Parallelität hochziehen heisst mehr Shops gleichzeitig, nicht mehr Zugriffe auf denselben Shop.
