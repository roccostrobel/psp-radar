"""Orchestrierung eines einzelnen Scans.

Gegenüber dem Vorgänger drei Änderungen:

1. **Trichter-Bewusstsein.** Jeder Scan meldet, in welcher Stufe das
   Ergebnis zustande kam. Wer "nur statisch erkannt" liest, kann selbst
   entscheiden, ob ihm das genügt.
2. **Früher Ausstieg.** Ein Live-Key im Quelltext oder ein PSP-Host in der
   CSP beweist den Anbieter. Die Checkout-Simulation danach kostet drei
   Minuten und ändert das Ergebnis nicht.
3. **Geteilter Browser.** Der Kontext wird von aussen hereingegeben, damit
   ein Massenlauf nicht pro Shop ein Chromium startet.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from playwright.async_api import BrowserContext

from .collect import (
    CheckoutOutcome,
    collect_rendered,
    collect_static,
    normalize,
    simulate_checkout,
)
from .config import ScanConfig
from .core import (
    Evidence,
    Observation,
    Registry,
    Role,
    ScanResult,
    Stage,
    fuse,
    load_registry,
    match_all,
)
from .core.models import ScanWarning
from .core.scoring import score_evidence


@dataclass
class Tier:
    """Die Stufen des Trichters, aufsteigend nach Aufwand."""

    STATIC = "statisch"
    RENDER = "gerendert"
    CHECKOUT = "checkout"


def _merge(target: dict[str, list[Evidence]], extra: dict[str, list[Evidence]]) -> None:
    for key, values in extra.items():
        target.setdefault(key, []).extend(values)


def best_platform_id(registry: Registry, evidence: dict[str, list[Evidence]]) -> str | None:
    """Frühe Plattformbestimmung — die Adapterwahl hängt davon ab."""
    best_id: str | None = None
    best_score = 0
    for signature in registry.platforms:
        found = evidence.get(signature.id)
        if not found:
            continue
        score, _ = score_evidence(found)
        if score > best_score:
            best_id, best_score = signature.id, score
    return best_id if best_score >= 45 else None


def gateway_confidence(registry: Registry, evidence: dict[str, list[Evidence]]) -> int:
    """Höchste Gateway-Confidence im aktuellen Zwischenstand."""
    best = 0
    for signature in registry.by_role(Role.GATEWAY, Role.ORCHESTRATOR):
        found = evidence.get(signature.id)
        if not found:
            continue
        score, _ = score_evidence(found)
        best = max(best, score)
    return best


async def scan(
    url: str,
    config: ScanConfig | None = None,
    *,
    context: BrowserContext | None = None,
) -> ScanResult:
    """Scannt einen Shop.

    `context` erlaubt es, einen bereits laufenden Browser mitzubenutzen.
    Im Massenlauf spart das pro Shop einen Prozessstart; ohne Angabe wird
    ein eigener Browser gestartet und danach geschlossen.
    """
    config = config or ScanConfig()
    registry = load_registry()
    started = time.monotonic()

    observations: list[Observation] = []
    warnings: list[ScanWarning] = []
    stages_run: list[Stage] = []
    evidence: dict[str, list[Evidence]] = {}
    tier = Tier.STATIC
    outcome: CheckoutOutcome | None = None

    # --- Stufe 0 ---
    normalized = await normalize(url, config)
    stages_run.append(Stage.NORMALIZE)
    warnings.extend(normalized.warnings)

    if not normalized.reachable:
        return _finish(registry, {}, url, normalized, False, stages_run, warnings, started, tier)

    # --- Stufe 1: billig, ohne Browser ---
    try:
        static_obs, static_warnings = await collect_static(normalized, config)
        observations.extend(static_obs)
        warnings.extend(static_warnings)
        stages_run.append(Stage.STATIC)
    except Exception as exc:  # ein Shop darf den Lauf nie abbrechen
        warnings.append(
            ScanWarning(
                code="static_stage_error",
                message=f"Stufe 1 fehlgeschlagen: {exc.__class__.__name__}: {exc}",
                stage=Stage.STATIC,
            )
        )

    _merge(evidence, match_all(registry, observations))

    # --- Früher Ausstieg nach Stufe 1 ---
    # Der eigentliche Tempogewinn im Massenlauf. Zulässig nur, weil der
    # Schwellwert gegen das Golden-Set kalibriert ist und das Ergebnis
    # sichtbar trägt, aus welcher Stufe es stammt.
    if config.auto_depth:
        current = gateway_confidence(registry, evidence)
        if current >= config.skip_render_threshold:
            warnings.append(
                ScanWarning(
                    code="early_exit_static",
                    message=(
                        f"Bereits nach der statischen Prüfung eindeutig ({current}%). "
                        "Browser und Checkout übersprungen."
                    ),
                )
            )
            return _finish(
                registry, evidence, url, normalized, False, stages_run, warnings, started, tier
            )

    if not config.enable_render:
        return _finish(
            registry, evidence, url, normalized, False, stages_run, warnings, started, tier
        )

    # --- Stufe 2 und 3 ---
    from .collect.browser import browser_session

    async def run_browser_stages(ctx: BrowserContext, recorder: object) -> None:
        nonlocal tier, outcome
        render_obs, render_warnings, product_url = await collect_rendered(
            ctx, recorder, normalized, config  # type: ignore[arg-type]
        )
        observations.extend(render_obs)
        warnings.extend(render_warnings)
        stages_run.append(Stage.RENDER)
        tier = Tier.RENDER

        from .core import match_all

        _merge(evidence, match_all(registry, render_obs))
        platform_id = best_platform_id(registry, evidence)

        if not config.enable_checkout:
            return

        if config.auto_depth:
            current = gateway_confidence(registry, evidence)
            if current >= config.skip_checkout_threshold:
                warnings.append(
                    ScanWarning(
                        code="early_exit_render",
                        message=(
                            f"Nach dem Rendern eindeutig ({current}%). "
                            "Checkout-Simulation übersprungen."
                        ),
                    )
                )
                return

        outcome = await simulate_checkout(
            ctx,
            recorder,  # type: ignore[arg-type]
            normalized,
            config,
            platform_id=platform_id,
            product_url=product_url,
        )
        observations.extend(outcome.observations)
        warnings.extend(outcome.warnings)
        if outcome.reached_checkout_page:
            stages_run.append(Stage.CHECKOUT)
            tier = Tier.CHECKOUT

    try:
        if context is not None:
            from .collect.browser import Recorder

            recorder = Recorder()
            recorder.attach(context)
            await asyncio.wait_for(
                run_browser_stages(context, recorder), timeout=config.total_timeout
            )
        else:
            async with browser_session(config) as (ctx, recorder):
                await asyncio.wait_for(
                    run_browser_stages(ctx, recorder), timeout=config.total_timeout
                )
    except TimeoutError:
        warnings.append(
            ScanWarning(
                code="timeout",
                message=f"Zeitbudget von {config.total_timeout:.0f}s überschritten",
            )
        )
    except Exception as exc:
        warnings.append(_browser_warnung(exc))

    # Der Checkout gilt nur als erreicht, wenn die Simulation das meldet.
    # Nicht daraus ableiten, ob eine Observation die Stufe CHECKOUT trägt —
    # die wird auch beim Scheitern angelegt. Dieser Fehler kostete im
    # Vorgängerprojekt einen halben Tag Fehlersuche in der falschen Ecke.
    checkout_reached = bool(outcome and outcome.reached_checkout_page)

    return _finish(
        registry, evidence, url, normalized, checkout_reached, stages_run, warnings, started, tier,
        observations=observations,
    )


def _browser_warnung(exc: Exception) -> ScanWarning:
    """Übersetzt Browser-Startfehler in eine brauchbare Meldung.

    Playwrights Originalmeldung ist ein Pfad plus Stacktrace. In der
    Oberfläche sah das aus wie ein Erkennungsproblem, war aber ein
    fehlender Browser — und schickte die Fehlersuche in die falsche
    Richtung. Ein Werkzeug, das seine eigenen Störungen nicht benennen
    kann, verschwendet die Zeit dessen, der es benutzt.
    """
    text = str(exc)

    if "Executable doesn't exist" in text or "playwright install" in text:
        return ScanWarning(
            code="browser_fehlt",
            message=(
                "Chromium ist nicht installiert, deshalb konnten die Browser- und "
                "Checkout-Stufen nicht laufen. Das Ergebnis stützt sich allein auf "
                "die statische Prüfung und bleibt deshalb oft leer — der "
                "Zahlungsdienstleister wird meist erst im Checkout sichtbar. "
                "Abhilfe: 'psp-radar doctor' ausführen, dann "
                "'playwright install chromium'."
            ),
        )

    if "Timeout" in text and "launch" in text:
        return ScanWarning(
            code="browser_start_langsam",
            message=(
                "Chromium liess sich nicht rechtzeitig starten. Meist zu wenig "
                "Arbeitsspeicher — im Codespace hilft eine grössere Maschine."
            ),
        )

    return ScanWarning(
        code="browser_stage_error",
        message=f"Browser-Stufen fehlgeschlagen: {exc.__class__.__name__}: {exc}",
    )


def _finish(
    registry: Registry,
    evidence: dict[str, list[Evidence]],
    url: str,
    normalized: object,
    checkout_reached: bool,
    stages_run: list[Stage],
    warnings: list[ScanWarning],
    started: float,
    tier: str,
    *,
    observations: list[Observation] | None = None,
) -> ScanResult:
    """Letzter Abgleich und Fusion."""
    from .core import match_all

    if observations:
        evidence = match_all(
            registry, observations, detected_platform=best_platform_id(registry, evidence)
        )

    result = fuse(
        registry,
        evidence,
        url=url,
        final_url=getattr(normalized, "final_url", None),
        final_domain=getattr(normalized, "final_domain", None),
        checkout_reached=checkout_reached,
        stages_run=stages_run,
        warnings=warnings,
        duration_s=time.monotonic() - started,
    )
    result.tier = tier
    return result


def scan_sync(url: str, config: ScanConfig | None = None) -> ScanResult:
    """Synchroner Einstieg für Skripte."""
    return asyncio.run(scan(url, config))
