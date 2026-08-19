"""Stufe 0 — Normalisierung.

Klingt nach Formsache, entscheidet aber häufiger über das Ergebnis als man
denkt: Wer `beispielshop.de` scannt, statt der Weiterleitung nach
`www.beispielshop.de/de-de/` zu folgen, misst die falsche Seite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx

from ..config import ScanConfig
from ..core.models import ScanWarning, Stage


@dataclass
class NormalizeResult:
    """Was Stufe 0 über die Zieladresse herausgefunden hat."""

    input_url: str
    final_url: str
    final_domain: str
    reachable: bool
    status_code: int | None = None
    redirect_chain: list[str] = field(default_factory=list)
    robots: RobotFileParser | None = None
    warnings: list[ScanWarning] = field(default_factory=list)

    def may_fetch(self, url: str, user_agent: str, respect: bool = True) -> bool:
        """Ob robots.txt diesen Pfad erlaubt."""
        if not respect or self.robots is None:
            return True
        try:
            return self.robots.can_fetch(user_agent, url)
        except Exception:
            # Kaputte robots.txt darf einen Scan nicht verhindern
            return True


def canonical_url(raw: str) -> str:
    """Ergänzt fehlendes Schema und entfernt Fragmente."""
    raw = raw.strip()
    if not raw:
        raise ValueError("Leere URL")
    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    if not parsed.hostname:
        raise ValueError(f"Keine gültige Domain in {raw!r}")

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


async def _load_robots(client: httpx.AsyncClient, base: str) -> RobotFileParser | None:
    parsed = urlparse(base)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = await client.get(robots_url, timeout=8.0)
    except httpx.HTTPError:
        return None

    if response.status_code != 200:
        return None

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


async def normalize(url: str, config: ScanConfig) -> NormalizeResult:
    """Löst Redirects auf, prüft Erreichbarkeit und liest robots.txt."""
    warnings: list[ScanWarning] = []
    start = canonical_url(url)

    headers = {"User-Agent": config.user_agent, "Accept-Language": config.accept_language}

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=config.static_timeout,
        headers=headers,
        verify=True,
    ) as client:
        try:
            response = await client.get(start)
        except httpx.HTTPError as exc:
            # Zweiter Versuch über http:// — manche kleinen Shops haben
            # ein kaputtes oder abgelaufenes Zertifikat, sind aber erreichbar.
            fallback = start.replace("https://", "http://", 1)
            try:
                response = await client.get(fallback)
                warnings.append(
                    ScanWarning(
                        code="https_failed",
                        message=f"HTTPS nicht erreichbar ({exc.__class__.__name__}), HTTP verwendet",
                        stage=Stage.NORMALIZE,
                    )
                )
            except httpx.HTTPError as exc2:
                parsed = urlparse(start)
                return NormalizeResult(
                    input_url=url,
                    final_url=start,
                    final_domain=parsed.hostname or "",
                    reachable=False,
                    warnings=[
                        ScanWarning(
                            code="unreachable",
                            message=f"Shop nicht erreichbar: {exc2.__class__.__name__}: {exc2}",
                            stage=Stage.NORMALIZE,
                        )
                    ],
                )

        final_url = str(response.url)
        parsed = urlparse(final_url)
        chain = [str(r.url) for r in response.history]

        if response.status_code >= 400:
            warnings.append(
                ScanWarning(
                    code="http_error",
                    message=f"Startseite antwortet mit HTTP {response.status_code}",
                    stage=Stage.NORMALIZE,
                )
            )

        robots = await _load_robots(client, final_url)
        if robots is None:
            warnings.append(
                ScanWarning(
                    code="no_robots",
                    message="Keine robots.txt gefunden — Scan wird ohne Einschränkung fortgesetzt",
                    stage=Stage.NORMALIZE,
                )
            )

    return NormalizeResult(
        input_url=url,
        final_url=final_url,
        final_domain=(parsed.hostname or "").lower(),
        reachable=response.status_code < 400,
        status_code=response.status_code,
        redirect_chain=chain,
        robots=robots,
        warnings=warnings,
    )
