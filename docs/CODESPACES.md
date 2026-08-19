# Codespaces — zurückgestellt

**Stand 19.08.2026: Der lokale Weg ist der empfohlene.** Die Codespaces-Einrichtung liegt weiterhin im Repo und wird von der CI geprüft, hat aber zweimal in der Praxis nicht funktioniert. Dieses Dokument hält fest, was passiert ist — damit ein späterer Anlauf nicht dieselben Runden dreht.

---

## Was schiefging

### Anlauf 1 — Chromium fehlte

Alle Browser-Stufen scheiterten mit `BrowserType.launch: Executable doesn't exist`. Die Oberfläche zeigte „Kein Zahlungsdienstleister ermittelt" plus Playwright-Stacktrace.

Ursache: Das Setup lud Chromium per `playwright install --with-deps` nach. Dieser Befehl ruft intern `apt-get` auf und braucht Root. Im Codespace läuft der Benutzer ohne Root, der Befehl scheiterte, und wegen `set -e` brach das gesamte Skript ab.

### Anlauf 2 — halb angelegtes venv

`psp-radar: command not found`, und `.venv` existierte ohne `bin/activate`.

Ursache: Im Ubuntu-noble-Image fehlt `python3-venv`. `python3 -m venv .venv` legt das Verzeichnis an und bricht an `ensurepip` ab. Zusätzlich ist das System-Python nach PEP 668 gesperrt.

### Anlauf 3 — weiterhin Fehler

Nach der Umstellung auf Installation ohne venv trat erneut ein Fehler auf. Dieser ist **nicht diagnostiziert**, weil an dieser Stelle auf den lokalen Betrieb umgestellt wurde.

---

## Die eigentliche Lehre

Alle drei Fälle waren **Umgebungsprobleme, die wie Erkennungsprobleme aussahen**. Das ist die teuerste Form von Fehler: Man sucht nach fehlenden Signaturen, während der Browser gar nicht startet.

Zwei Dinge sind daraus entstanden und bleiben nützlich, unabhängig davon ob Codespaces je läuft:

- **`psp-radar doctor`** prüft Python, Signaturen, Chromium (ob der Browser *startet*, nicht nur ob die Datei existiert), Netzwerk und Zugangscode. Läuft im lokalen Starter automatisch vor jedem Serverstart.
- **Browser-Startfehler werden in Klartext übersetzt** statt als Stacktrace gezeigt, mit dem ausdrücklichen Hinweis, dass leere Ergebnisse dann eine Folge des fehlenden Browsers sind.

Ein dritter Punkt war der Verfahrensfehler: Die Codespace-Einrichtung war die einzige ungetestete Stelle im Projekt, und genau dort traten die Fehler auf. Der CI-Job `devcontainer` prüft sie jetzt — dasselbe Image, dasselbe Setup-Skript, vollständiger Selbsttest, Serverstart und ein echter Scan. Dass dieser Job grün ist, während der echte Codespace scheitert, bedeutet: Es gibt einen Unterschied zwischen GitHub-Actions-Container und Codespace, den ich noch nicht kenne.

---

## Wenn jemand es erneut versucht

Zuerst diese Frage beantworten, bevor irgendetwas geändert wird:

> Warum läuft dasselbe Image mit demselben Skript in GitHub Actions durch, aber nicht im Codespace?

Kandidaten, ungeprüft:

- Codespaces setzt eigene Umgebungsvariablen und einen anderen Benutzer als der Actions-Container
- Der Arbeitsbereich liegt unter `/workspaces/...` mit anderen Rechten
- `postCreateCommand` und `postStartCommand` laufen in einer anderen Shell und mit anderem PATH als `run:` in Actions
- Ein vorhandener Codespace behält sein altes Image; „neu starten" genügt nicht, es muss gelöscht und neu erstellt werden

Vorgehen: Codespace erstellen, **nichts** eingeben, sondern zuerst das vollständige Setup-Protokoll sichern:

```bash
cat /workspaces/.codespaces/.persistedshare/creation.log
```

Darin steht, ob und wo `postCreateCommand` gescheitert ist. Ohne dieses Protokoll ist jede weitere Änderung geraten — und geraten wurde in diesem Projekt schon zu oft.
