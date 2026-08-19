"""SQLite-Speicher für Scan-Ergebnisse.

Für Einzelabfragen optional, für Massenläufe unverzichtbar: Ein
abgebrochener Batch soll dort weitermachen, wo er stehengeblieben ist,
statt tausend Shops erneut zu behelligen. Das ist gleichzeitig
Effizienz- und Anstandsfrage.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..core.models import ScanResult

DEFAULT_DB = Path("scans.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    final_domain    TEXT,
    platform        TEXT,
    psp             TEXT,
    psp_confidence  INTEGER,
    checkout_reached INTEGER NOT NULL DEFAULT 0,
    overall_confidence INTEGER NOT NULL DEFAULT 0,
    signature_version TEXT,
    scanned_at      TEXT    NOT NULL,
    payload         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scans_domain  ON scans(final_domain);
CREATE INDEX IF NOT EXISTS idx_scans_url     ON scans(url);
CREATE INDEX IF NOT EXISTS idx_scans_scanned ON scans(scanned_at);
"""


@contextmanager
def connect(path: Path | str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(_SCHEMA)
        yield connection
        connection.commit()
    finally:
        connection.close()


def save(result: ScanResult, path: Path | str = DEFAULT_DB) -> int:
    """Speichert ein Ergebnis und gibt die Zeilen-ID zurück."""
    primary = result.primary_psp
    with connect(path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO scans (
                url, final_domain, platform, psp, psp_confidence,
                checkout_reached, overall_confidence, signature_version,
                scanned_at, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.url,
                result.final_domain,
                result.platform.name if result.platform else None,
                primary.name if primary else None,
                primary.confidence if primary else None,
                int(result.checkout_reached),
                result.overall_confidence,
                result.signature_version,
                result.scanned_at.isoformat(),
                result.model_dump_json(),
            ),
        )
        return int(cursor.lastrowid or 0)


def find_recent(
    url: str, max_age_days: int = 30, path: Path | str = DEFAULT_DB
) -> ScanResult | None:
    """Sucht ein hinreichend frisches Ergebnis im Cache.

    Verhindert, dass ein Massenlauf denselben Shop mehrfach anfasst.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
    with connect(path) as connection:
        row = connection.execute(
            "SELECT payload FROM scans WHERE url = ? AND scanned_at >= ? "
            "ORDER BY scanned_at DESC LIMIT 1",
            (url, cutoff),
        ).fetchone()

    if row is None:
        return None
    return ScanResult.model_validate(json.loads(row["payload"]))


def stats(path: Path | str = DEFAULT_DB) -> dict[str, int | dict[str, int]]:
    """Verteilung der bisher erkannten PSPs — die eigentliche Marktübersicht."""
    with connect(path) as connection:
        total = connection.execute("SELECT COUNT(*) AS n FROM scans").fetchone()["n"]
        reached = connection.execute(
            "SELECT COUNT(*) AS n FROM scans WHERE checkout_reached = 1"
        ).fetchone()["n"]
        identified = connection.execute(
            "SELECT COUNT(*) AS n FROM scans WHERE psp IS NOT NULL"
        ).fetchone()["n"]
        by_psp = {
            row["psp"]: row["n"]
            for row in connection.execute(
                "SELECT psp, COUNT(*) AS n FROM scans WHERE psp IS NOT NULL "
                "GROUP BY psp ORDER BY n DESC"
            )
        }
        by_platform = {
            row["platform"]: row["n"]
            for row in connection.execute(
                "SELECT platform, COUNT(*) AS n FROM scans WHERE platform IS NOT NULL "
                "GROUP BY platform ORDER BY n DESC"
            )
        }

    return {
        "scans_gesamt": total,
        "checkout_erreicht": reached,
        "psp_erkannt": identified,
        "nach_psp": by_psp,
        "nach_shopsystem": by_platform,
    }
