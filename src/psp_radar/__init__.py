"""psp-radar — ermittelt Zahlungsdienstleister hinter Shop-URLs.

Nachfolger von psp-detector. Zwei Unterschiede: teilbar ohne Installation,
und schnell genug für Listen.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import ScanConfig
from .core import Detection, Evidence, Observation, Role, ScanResult, Stage
from .scanner import scan, scan_sync

__all__ = [
    "Detection",
    "Evidence",
    "Observation",
    "Role",
    "ScanConfig",
    "ScanResult",
    "Stage",
    "__version__",
    "scan",
    "scan_sync",
]
