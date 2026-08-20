"""Abgleich von Observations gegen die Signatur-Datenbank.

Hier wird aus Rohmaterial Evidenz. Jede Übereinstimmung notiert, *was*
genau wo gefunden wurde — nicht nur, dass etwas gefunden wurde. Ohne diesen
Nachweis wäre jedes Ergebnis eine Behauptung statt eines Befunds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from urllib.parse import urlparse

from .models import Evidence, Role, Signal, SignalType, Signature
from .observation import Observation
from .registry import Registry


@lru_cache(maxsize=2048)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def host_matches(host: str, pattern: str) -> bool:
    """Exakter Host oder echte Subdomain.

    Bewusst streng: `evilapi.stripe.com` darf nicht als `api.stripe.com`
    durchgehen, und `notstripe.com` nicht als `stripe.com`. Solche
    Beinahe-Treffer sind die häufigste Ursache für Fehlalarme.
    """
    host = host.lower().lstrip(".")
    pattern = pattern.lower().lstrip("*").lstrip(".")
    return host == pattern or host.endswith("." + pattern)


def _iter_matches(signal: Signal, obs: Observation) -> Iterable[str]:
    """Liefert die konkret gefundenen Werte für ein Signal, oder nichts."""
    match signal.type:
        case SignalType.NETWORK_HOST:
            for host in obs.network_hosts():
                if host_matches(host, signal.pattern):
                    yield host

        case SignalType.NETWORK_URL_REGEX:
            rx = _compiled(signal.pattern)
            seen: set[str] = set()
            for url in (*obs.network_urls, *obs.script_srcs, *obs.iframe_srcs):
                if rx.search(url) and url not in seen:
                    seen.add(url)
                    yield url[:300]

        case SignalType.HTML_REGEX:
            match = _compiled(signal.pattern).search(obs.html)
            if match:
                yield match.group(0)[:200]

        case SignalType.SCRIPT_SRC:
            rx = _compiled(signal.pattern)
            for src in obs.script_srcs:
                if rx.search(src):
                    yield src[:300]

        case SignalType.IFRAME_SRC:
            rx = _compiled(signal.pattern)
            for src in obs.iframe_srcs:
                if rx.search(src):
                    yield src[:300]

        case SignalType.CSP_DOMAIN:
            for domain in obs.csp_domains:
                if host_matches(domain, signal.pattern):
                    yield domain

        case SignalType.COOKIE:
            rx = _compiled(signal.pattern)
            for name in obs.cookies:
                if rx.search(name):
                    yield name

        case SignalType.HEADER:
            # Format "header-name:regex"
            name, _, value_pattern = signal.pattern.partition(":")
            actual = obs.headers.get(name.strip().lower())
            if actual is not None and _compiled(value_pattern.strip() or ".").search(actual):
                yield f"{name.strip()}: {actual[:150]}"

        case SignalType.JS_GLOBAL:
            for name in obs.js_globals:
                if name == signal.pattern:
                    yield name

        case SignalType.DOM_TEXT:
            match = _compiled(signal.pattern).search(obs.dom_text)
            if match:
                yield match.group(0)[:120]

        case SignalType.PAYMENT_PAGE_TEXT:
            # Greift ausschliesslich auf Zahlungsinformationsseiten. Genau
            # diese Einschränkung erlaubt das hohe Gewicht: Sonst würde ein
            # Blogartikel über Stripe einen Stripe-Treffer erzeugen.
            if not obs.is_payment_page:
                return
            match = _compiled(signal.pattern).search(obs.dom_text)
            if match:
                # Etwas Kontext mitgeben, damit im Report nachlesbar ist,
                # in welchem Satz der Anbieter genannt wurde.
                start = max(0, match.start() - 60)
                yield obs.dom_text[start : match.end() + 60].strip()

        case SignalType.WELLKNOWN:
            for path in obs.wellknown_hits:
                if path == signal.pattern:
                    yield path


def match_signature(
    signature: Signature, observations: Iterable[Observation]
) -> list[Evidence]:
    """Sammelt alle Evidenz für eine Signatur über alle Observations."""
    evidence: list[Evidence] = []

    for obs in observations:
        for signal in signature.signals:
            if signal.stages is not None and obs.stage not in signal.stages:
                continue
            for value in _iter_matches(signal, obs):
                evidence.append(
                    Evidence(
                        signature_id=signature.id,
                        signal_type=signal.type,
                        pattern=signal.pattern,
                        matched_value=value,
                        weight=signal.weight,
                        stage=obs.stage,
                        source_url=obs.source_url,
                    )
                )
                break  # ein Treffer pro Signal und Observation genügt

    return evidence


def match_all(
    registry: Registry,
    observations: Iterable[Observation],
    *,
    detected_platform: str | None = None,
    only_roles: tuple[Role, ...] | None = None,
) -> dict[str, list[Evidence]]:
    """Gleicht alle Signaturen ab und gruppiert die Evidenz nach Signatur-ID.

    `detected_platform` filtert Signaturen mit `requires_platform`. Ohne
    diesen Filter würde etwa Shopify Payments auch bei einem WooCommerce-Shop
    anschlagen, sobald dort zufällig ein Shopify-Asset eingebunden ist.

    `only_roles` beschränkt den Abgleich auf bestimmte Rollen. Der Grund ist
    Laufzeit, nicht Eleganz: Die Plattformerkennung, die vor dem eigentlichen
    Abgleich laufen muss, braucht nur die Plattform-Signaturen. Ohne diese
    Einschränkung wurde die gesamte Signaturdatenbank zweimal über alle
    Observations gerechnet — bei einem Shop mit mehreren Megabyte HTML sind
    das zwanzig Sekunden, die nichts beitragen.
    """
    obs_list = list(observations)
    for obs in obs_list:
        obs.merge_csp_from_headers()

    results: dict[str, list[Evidence]] = {}

    for signature in registry.signatures:
        if only_roles is not None and signature.role not in only_roles:
            continue
        if signature.requires_platform and signature.requires_platform != detected_platform:
            continue
        evidence = match_signature(signature, obs_list)
        if evidence:
            results[signature.id] = evidence

    return results


def same_site(url_a: str, url_b: str) -> bool:
    """Ob zwei URLs zur selben registrierbaren Domain gehören."""
    host_a = (urlparse(url_a).hostname or "").lower()
    host_b = (urlparse(url_b).hostname or "").lower()
    if not host_a or not host_b:
        return False
    return host_a == host_b or host_a.endswith("." + host_b) or host_b.endswith("." + host_a)
