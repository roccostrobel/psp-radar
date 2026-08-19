"""Plattform-Adapter für die Checkout-Simulation.

Ein erkanntes Shop-System bekommt seinen spezialisierten Adapter mit
bekannten Selektoren und API-Pfaden. Alles andere fällt auf die generische
Heuristik zurück — die ist schwächer, aber besser als nichts.
"""

from __future__ import annotations

from .base import CheckoutAdapter, is_forbidden_label, safe_click
from .oxid import OxidAdapter
from .shopify import ShopifyAdapter
from .shopware import ShopwareAdapter
from .woocommerce import WooCommerceAdapter

#: Reihenfolge egal — die Zuordnung läuft über platform_id
ADAPTERS: tuple[type[CheckoutAdapter], ...] = (
    ShopifyAdapter,
    WooCommerceAdapter,
    ShopwareAdapter,
    OxidAdapter,
)

_BY_PLATFORM = {a.platform_id: a for a in ADAPTERS if a.platform_id}


def pick_adapter(platform_id: str | None) -> CheckoutAdapter:
    """Wählt den passenden Adapter, sonst den generischen."""
    adapter_class = _BY_PLATFORM.get(platform_id or "", CheckoutAdapter)
    return adapter_class()


__all__ = [
    "ADAPTERS",
    "CheckoutAdapter",
    "OxidAdapter",
    "ShopifyAdapter",
    "ShopwareAdapter",
    "WooCommerceAdapter",
    "is_forbidden_label",
    "pick_adapter",
    "safe_click",
]
