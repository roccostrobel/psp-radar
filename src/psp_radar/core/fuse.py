"""Stufe 4 — Fusion.

Hier wird aus Evidenz ein Urteil. Drei Dinge passieren, und alle drei
entscheiden über die Qualität des Ergebnisses:

1. **Scoring** — Noisy-OR mit Dämpfung statt Addition (siehe scoring.py).
2. **Konfliktauflösung** — Shopify Payments verdrängt Stripe, weil Stripe
   dort nur der technische Unterbau ist. Ohne diesen Schritt meldet das
   Tool zwei Gateways, wo faktisch eines abrechnet.
3. **Rollentrennung** — PayPal und Klarna landen bei den Zahlungsarten,
   nicht bei den Gateways. Das ist der Unterschied zwischen "welche
   Buttons sehe ich" und "wer wickelt ab".
"""

from __future__ import annotations

from .models import Detection, Evidence, Role, ScanResult, ScanWarning, Stage
from .registry import Registry
from .scoring import REPORT_FLOOR, checkout_bonus, score_evidence


def _build_detection(
    registry: Registry, signature_id: str, evidence: list[Evidence]
) -> Detection | None:
    signature = registry.get(signature_id)
    if signature is None:
        return None

    score, deduped = score_evidence(evidence)
    saw_checkout = any(e.stage == Stage.CHECKOUT for e in deduped)
    score = checkout_bonus(score, saw_checkout)

    underlying = registry.get(signature.underlying) if signature.underlying else None

    return Detection(
        id=signature.id,
        name=signature.name,
        role=signature.role,
        confidence=score,
        underlying=signature.underlying,
        underlying_name=underlying.name if underlying else signature.underlying,
        evidence=deduped[:12],  # die aussagekräftigsten Belege genügen im Report
    )


def _resolve_conflicts(
    registry: Registry, detections: dict[str, Detection]
) -> dict[str, Detection]:
    """Unterdrückt Signaturen, die von einer spezifischeren verdrängt werden.

    Beispiel Shopify Payments: Der Traffic geht an Stripe-Infrastruktur,
    kaufmännisch ist der Vertragspartner aber Shopify. Beides zu melden
    wäre nicht falsch, aber irreführend — also wird Stripe zum `underlying`
    degradiert statt als eigenständiges Gateway geführt.
    """
    suppressed: set[str] = set()

    for detection in detections.values():
        signature = registry.get(detection.id)
        if signature is None or detection.confidence < 60:
            continue
        for target in signature.supersedes:
            if target in detections:
                suppressed.add(target)

    return {k: v for k, v in detections.items() if k not in suppressed}


def _detect_platform(
    registry: Registry, evidence_by_id: dict[str, list[Evidence]]
) -> Detection | None:
    """Bestimmt das wahrscheinlichste Shop-System.

    Bewusst nur *ein* Ergebnis: Ein Shop läuft auf genau einem System.
    Mehrere Treffer bedeuten Rauschen, nicht Vielfalt.
    """
    candidates: list[Detection] = []
    for signature in registry.platforms:
        evidence = evidence_by_id.get(signature.id)
        if not evidence:
            continue
        detection = _build_detection(registry, signature.id, evidence)
        if detection and detection.confidence >= 45:
            candidates.append(detection)

    return max(candidates, key=lambda d: d.confidence, default=None)


def fuse(
    registry: Registry,
    evidence_by_id: dict[str, list[Evidence]],
    *,
    url: str,
    final_url: str | None,
    final_domain: str | None,
    checkout_reached: bool,
    stages_run: list[Stage],
    warnings: list[ScanWarning],
    duration_s: float,
) -> ScanResult:
    """Verdichtet alle Evidenz zum Endergebnis."""
    platform = _detect_platform(registry, evidence_by_id)

    detections: dict[str, Detection] = {}
    for signature_id, evidence in evidence_by_id.items():
        signature = registry.get(signature_id)
        if signature is None or signature.role == Role.PLATFORM:
            continue
        detection = _build_detection(registry, signature_id, evidence)
        if detection and detection.confidence >= REPORT_FLOOR:
            detections[signature_id] = detection

    detections = _resolve_conflicts(registry, detections)

    def bucket(*roles: Role) -> list[Detection]:
        items = [d for d in detections.values() if d.role in roles]
        return sorted(items, key=lambda d: -d.confidence)

    psps = bucket(Role.GATEWAY, Role.ORCHESTRATOR)
    methods = bucket(Role.METHOD)
    wallets = bucket(Role.WALLET)
    fraud = bucket(Role.FRAUD)

    result = ScanResult(
        url=url,
        final_url=final_url,
        final_domain=final_domain,
        platform=platform,
        psps=psps,
        payment_methods=methods,
        wallets=wallets,
        fraud_tools=fraud,
        checkout_reached=checkout_reached,
        stages_run=stages_run,
        warnings=list(warnings),
        duration_s=round(duration_s, 1),
        signature_version=registry.version,
    )

    result.overall_confidence = _overall_confidence(result)
    _add_interpretation_warnings(result)
    return result


def _overall_confidence(result: ScanResult) -> int:
    """Wie sicher ist die Kernaussage — also der PSP?

    Ohne erreichten Checkout wird gedeckelt. Die Begründung ist schlicht:
    Wer den Checkout nicht gesehen hat, kann nicht wissen, was dort
    passiert, und sollte das auch nicht behaupten.
    """
    primary = result.primary_psp
    if primary is None:
        return 0
    if not result.checkout_reached:
        return min(primary.confidence, 82)
    return primary.confidence


def _add_interpretation_warnings(result: ScanResult) -> None:
    """Ergänzt Hinweise, die vor Fehldeutung des Ergebnisses schützen."""
    if not result.psps:
        result.warnings.append(
            ScanWarning(
                code="no_psp_found",
                message=(
                    "Kein Zahlungsdienstleister erkannt. Mögliche Gründe: unbekannter "
                    "Anbieter (Signatur fehlt), Checkout nicht erreichbar, oder der Shop "
                    "leitet zur Zahlung auf eine externe Domain um."
                ),
            )
        )

    gateways = [d for d in result.psps if d.role == Role.GATEWAY]
    if len(gateways) > 1 and gateways[0].confidence - gateways[1].confidence < 15:
        names = ", ".join(d.name for d in gateways[:3])
        result.warnings.append(
            ScanWarning(
                code="ambiguous_psp",
                message=(
                    f"Mehrere Gateways mit ähnlicher Confidence erkannt ({names}). "
                    "Das kann auf eine Multi-PSP-Strategie hindeuten oder auf ein "
                    "Signalproblem — Belege prüfen."
                ),
            )
        )

    if result.checkout_reached and not result.psps:
        result.warnings.append(
            ScanWarning(
                code="checkout_without_psp",
                message=(
                    "Checkout wurde erreicht, aber kein bekannter PSP erkannt. "
                    "Starker Hinweis auf eine fehlende Signatur — die Netzwerk-Hosts "
                    "im Checkout lohnen eine manuelle Sichtung."
                ),
                stage=Stage.CHECKOUT,
            )
        )
