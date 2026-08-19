"""Das Rohmaterial, das die Pipeline-Stufen einsammeln.

Eine Observation ist ein neutraler Mitschnitt dessen, was auf einer Seite
tatsächlich passiert ist: welche Requests liefen, welche Cookies gesetzt
wurden, was im HTML stand. Keine Interpretation — die kommt später.

Diese Trennung ist der Grund, warum sich das Tool offline testen lässt:
Observations sind serialisierbar. Einmal aufgezeichnet, lassen sie sich
als Fixture einfrieren und die gesamte Erkennungslogik deterministisch
gegen sie prüfen, ohne je wieder einen echten Shop anzufassen.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .models import Stage

_CSP_DIRECTIVES = ("connect-src", "frame-src", "script-src", "form-action", "default-src")


class Observation(BaseModel):
    """Mitschnitt einer einzelnen betrachteten Seite."""

    stage: Stage
    source_url: str

    html: str = ""
    #: Response-Header, Schlüssel klein geschrieben
    headers: dict[str, str] = Field(default_factory=dict)
    #: Cookie-Name -> Wert
    cookies: dict[str, str] = Field(default_factory=dict)

    #: Alle beobachteten Request-URLs (nur Stufe 2/3)
    network_urls: list[str] = Field(default_factory=list)
    script_srcs: list[str] = Field(default_factory=list)
    iframe_srcs: list[str] = Field(default_factory=list)
    #: Aus der CSP extrahierte Hosts
    csp_domains: list[str] = Field(default_factory=list)
    #: Im Browser vorhandene globale JS-Objekte
    js_globals: list[str] = Field(default_factory=list)
    #: Sichtbarer Text (schwaches Signal, nur zur Stützung)
    dom_text: str = ""
    #: Erfolgreich abgerufene bekannte Pfade
    wellknown_hits: list[str] = Field(default_factory=list)

    def network_hosts(self) -> set[str]:
        """Alle Hostnamen aus beobachteten Requests, iframes und Skripten."""
        hosts: set[str] = set()
        for url in (*self.network_urls, *self.script_srcs, *self.iframe_srcs):
            host = urlparse(url).hostname
            if host:
                hosts.add(host.lower())
        return hosts

    def merge_csp_from_headers(self) -> None:
        """Zieht Hosts aus dem Content-Security-Policy-Header.

        Die CSP ist die unterschätzteste Quelle überhaupt: Ein Shop muss
        dort jede Domain whitelisten, mit der sein Checkout spricht —
        auch die, die erst später geladen wird. Ein
        `frame-src https://*.adyen.com` verrät den Zahlungsdienstleister,
        bevor man den Warenkorb überhaupt gesehen hat.
        """
        policy = self.headers.get("content-security-policy", "")
        policy += " " + self.headers.get("content-security-policy-report-only", "")
        if not policy.strip():
            return

        found: set[str] = set()
        for chunk in policy.split(";"):
            parts = chunk.strip().split()
            if not parts or parts[0].lower() not in _CSP_DIRECTIVES:
                continue
            for token in parts[1:]:
                token = token.strip().strip("'\"")
                if token.startswith(("'", "data:", "blob:", "http:", "https:")) and "." not in token:
                    continue
                host = token.removeprefix("https://").removeprefix("http://").split("/")[0]
                if "." in host:
                    found.add(host.lower())

        self.csp_domains = sorted(set(self.csp_domains) | found)


def extract_srcs(html: str) -> tuple[list[str], list[str]]:
    """Holt script-src und iframe-src direkt aus dem HTML.

    Bewusst regexbasiert und fehlertolerant: In Stufe 1 liegt oft kein
    valides HTML vor, und ein strenger Parser würde an kaputtem Markup
    scheitern — ausgerechnet bei den Shops, die uns interessieren.
    """
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return scripts, iframes


def strip_tags(html: str, limit: int = 200_000) -> str:
    """Grober Textauszug für DOM_TEXT-Signale."""
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", html[:limit], flags=re.IGNORECASE | re.DOTALL
    )
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", without_scripts)).strip()
