"""Farb- und Typografiewerte im Unzer-Corporate-Design.

Nicht geschätzt, sondern ausgelesen: `scripts/extract_brand.py` rendert
unzer.com und wertet die berechneten Stile aus. Die Werte unten stammen aus
diesem Lauf (Stand August 2026).

Zur Schrift: Unzer setzt **Visuelt** ein, eine lizenzpflichtige Schrift von
Colophon Foundry. Sie lässt sich nicht mitliefern. Die Schriftliste ist
deshalb so aufgebaut, dass Visuelt automatisch greift, wenn sie auf dem
Rechner installiert ist — auf Unzer-Arbeitsplätzen also von allein. Sonst
fällt sie sauber auf die Systemschrift zurück, die im Charakter nah genug ist.
"""

from __future__ import annotations

#: Primärfarbe. Auf unzer.com die Farbe jedes Call-to-Action-Buttons.
RASPBERRY = "#fc1154"
RASPBERRY_DARK = "#d4083f"

#: Dunkle Markenfarbe für Text und dunkle Flächen.
NAVY = "#0c1332"

#: Sekundärtöne aus dem Seitenrendering.
MIST = "#a8bdca"
GREY = "#86899a"
LINK_BLUE = "#1b6ad7"

#: Formsprache: vollrunde Buttons, grosszügig gerundete Karten.
RADIUS_PILL = "9999px"
RADIUS_CARD = "20px"
RADIUS_INPUT = "9999px"

FONT_STACK = (
    "'Visuelt Pro', 'Visuelt', 'VisueltPro', Inter, "
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
)

#: Überschriften laufen bei Unzer deutlich negativ (-4px auf 100px ≈ -0.04em).
HEADING_TRACKING = "-0.035em"
