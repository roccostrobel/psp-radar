"""HTTP-Schnittstelle mit Zugangscode.

Enthält keine Erkennungslogik — nur Jobverwaltung, Fortschritt und Export.
Dadurch lässt sich derselbe Kern unverändert per CLI, im Codespace oder auf
einem Server betreiben.

**Zum Zugangscode:** Im Codespace ist der weitergeleitete Port privat und
nur für den angemeldeten Nutzer erreichbar — dort ist kein Code nötig, und
`PSP_RADAR_ACCESS_CODE` bleibt leer. Sobald das Ganze öffentlich erreichbar
läuft, ist der Code Pflicht. Ein offener Scanner, der fremde Checkouts
durchklickt, wird gefunden und missbraucht, und dann klopft der Server im
Minutentakt bei fremden Händlern an.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..batch import BatchProgress, run_batch
from ..config import ScanConfig
from ..core import ScanResult, load_registry
from ..report import results_to_csv
from ..scanner import scan
from ..web import render_index

#: Leer = kein Code verlangt (Codespaces, lokal). Gesetzt = Pflicht.
ACCESS_CODE = os.environ.get("PSP_RADAR_ACCESS_CODE", "").strip()

#: Pfade, die ohne Code erreichbar bleiben müssen
OPEN_PATHS = frozenset({"/api/health", "/favicon.ico"})

#: Schätzwerte für den Fortschrittsbalken, nach Modus
ESTIMATED_SECONDS = {"voll": 110.0, "schnell": 25.0, "trichter": 60.0, "statisch": 6.0}


@dataclass
class Job:
    id: str
    kind: Literal["single", "batch"]
    label: str
    mode: str
    status: Literal["laeuft", "fertig", "fehler"] = "laeuft"
    started_at: float = field(default_factory=time.monotonic)
    result: ScanResult | None = None
    results: list[ScanResult] = field(default_factory=list)
    progress: BatchProgress | None = None
    error: str | None = None
    stage: str = "wird gestartet"

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def payload(self) -> dict[str, Any]:
        if self.kind == "batch" and self.progress is not None:
            fraction = self.progress.percent
        else:
            estimate = ESTIMATED_SECONDS.get(self.mode, 110.0)
            fraction = min(0.97, self.elapsed / estimate) if self.status == "laeuft" else 1.0

        data: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "stage": self.stage,
            "elapsed": round(self.elapsed, 1),
            "progress": 1.0 if self.status != "laeuft" else fraction,
            "error": self.error,
        }
        if self.kind == "single":
            data["result"] = json.loads(self.result.model_dump_json()) if self.result else None
        else:
            data["done"] = self.progress.done if self.progress else 0
            data["total"] = self.progress.total if self.progress else 0
            data["nach_stufe"] = dict(self.progress.tier_counts) if self.progress else {}
            data["results"] = [json.loads(r.model_dump_json()) for r in self.results]
        return data


class ScanRequest(BaseModel):
    url: str = Field(min_length=3)
    mode: Literal["trichter", "voll", "schnell", "statisch"] = "trichter"


class BatchRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=500)
    mode: Literal["trichter", "voll", "schnell", "statisch"] = "trichter"
    concurrency: int = Field(default=6, ge=1, le=16)


def _config_for(mode: str, concurrency: int = 6) -> ScanConfig:
    """Übersetzt den gewählten Modus in eine Konfiguration."""
    match mode:
        case "statisch":
            # Kein Browser. Wenige Sekunden, reicht überraschend oft:
            # CSP-Header und die Zahlungsinformationsseite sind stark.
            return ScanConfig(
                enable_render=False,
                enable_checkout=False,
                total_timeout=45.0,
                concurrency=concurrency,
            )
        case "schnell":
            return ScanConfig(
                enable_render=True,
                enable_checkout=False,
                total_timeout=90.0,
                concurrency=concurrency,
            )
        case "voll":
            return ScanConfig(auto_depth=False, total_timeout=280.0, concurrency=concurrency)
        case _:  # trichter
            return ScanConfig(auto_depth=True, total_timeout=200.0, concurrency=concurrency)


def build_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="psp-radar", docs_url=None, redoc_url=None)
    jobs: dict[str, Job] = {}

    @app.middleware("http")
    async def check_access(request: Request, call_next: Any) -> Any:
        """Zugangsprüfung per Cookie oder Header.

        Absichtlich schlicht: ein gemeinsames Geheimnis, verglichen in
        konstanter Zeit. Kein Nutzerkonto, keine Sitzungsverwaltung — für
        internen Gebrauch angemessen, und was nicht existiert, kann auch
        nicht falsch konfiguriert werden.
        """
        if not ACCESS_CODE or request.url.path in OPEN_PATHS:
            return await call_next(request)

        supplied = request.headers.get("x-access-code") or request.cookies.get("psp_radar_code", "")
        if secrets.compare_digest(supplied, ACCESS_CODE):
            return await call_next(request)

        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Zugangscode fehlt oder ist falsch"}, status_code=401)
        return HTMLResponse(_LOGIN_HTML, status_code=401)

    async def run_single(job: Job, url: str) -> None:
        config = _config_for(job.mode)
        try:
            job.stage = "Shop wird geprüft"
            job.result = await scan(url, config)
            job.status = "fertig"
            job.stage = f"abgeschlossen ({job.result.tier})"
        except Exception as exc:
            job.status, job.error, job.stage = "fehler", f"{exc.__class__.__name__}: {exc}", "abgebrochen"

    async def run_many(job: Job, urls: list[str], concurrency: int) -> None:
        config = _config_for(job.mode, concurrency)
        job.progress = BatchProgress(total=len(urls))

        def on_progress(progress: BatchProgress) -> None:
            # Das Fortschrittsobjekt wird von run_batch selbst angelegt und
            # hier übernommen. Ohne diese Zuweisung zeigte die Oberfläche
            # dauerhaft "0 von N", während die Ergebnisse längst eintrafen —
            # die API sah ein anderes Objekt als der Worker.
            job.progress = progress
            job.stage = f"{progress.done} von {progress.total} — {progress.current}"

        try:
            job.results = await run_batch(
                urls, config, db_path=db_path, on_progress=on_progress
            )
            job.status = "fertig"
            job.stage = "abgeschlossen"
        except Exception as exc:
            job.status, job.error, job.stage = "fehler", f"{exc.__class__.__name__}: {exc}", "abgebrochen"

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        stats = load_registry().stats()
        return render_index(int(stats["total"]), int(stats.get("gateway", 0)))

    @app.post("/api/scan")
    async def start_scan(request: ScanRequest) -> JSONResponse:
        job = Job(id=uuid.uuid4().hex[:12], kind="single", label=request.url.strip(), mode=request.mode)
        jobs[job.id] = job
        asyncio.create_task(run_single(job, job.label))  # noqa: RUF006
        return JSONResponse({"id": job.id})

    @app.post("/api/batch")
    async def start_batch(request: BatchRequest) -> JSONResponse:
        urls = _dedupe([u.strip() for u in request.urls if u.strip()])
        job = Job(
            id=uuid.uuid4().hex[:12],
            kind="batch",
            label=f"{len(urls)} Shops",
            mode=request.mode,
        )
        jobs[job.id] = job
        asyncio.create_task(run_many(job, urls, request.concurrency))  # noqa: RUF006
        return JSONResponse({"id": job.id, "anzahl": len(urls)})

    @app.get("/api/job/{job_id}")
    async def poll(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unbekannter Auftrag")
        return job.payload()

    @app.get("/api/job/{job_id}/csv", response_class=PlainTextResponse)
    async def export_csv(job_id: str) -> PlainTextResponse:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unbekannter Auftrag")

        rows = job.results if job.kind == "batch" else ([job.result] if job.result else [])
        return PlainTextResponse(
            results_to_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="psp-radar-{job_id}.csv"'},
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __import__("psp_radar").__version__,
            "signaturen": load_registry().stats(),
            "zugangscode_aktiv": bool(ACCESS_CODE),
        }

    return app


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def serve(host: str = "127.0.0.1", port: int = 8765, db_path: Path | None = None) -> None:
    import uvicorn

    uvicorn.run(build_app(db_path), host=host, port=port, log_level="warning")


_LOGIN_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>psp-radar</title><style>
body{font:16px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;background:#f4f6f8;
color:#0c1332;display:grid;place-items:center;min-height:100vh;margin:0}
.box{background:#fff;padding:32px;border-radius:20px;max-width:380px;
box-shadow:0 8px 28px rgba(12,19,50,.08)}
h1{font-size:20px;margin:0 0 6px;letter-spacing:-.03em}
p{color:rgba(12,19,50,.7);font-size:14.5px;margin:0 0 20px}
input{width:100%;padding:14px 20px;border:1.5px solid rgba(12,19,50,.12);
border-radius:9999px;font:inherit;margin-bottom:12px;box-sizing:border-box}
input:focus{outline:none;border-color:#fc1154}
button{width:100%;padding:14px;background:#fc1154;color:#fff;border:0;
border-radius:9999px;font:inherit;font-weight:700;cursor:pointer}
</style></head><body><div class="box">
<h1>psp-radar</h1><p>Interner Zugang — bitte Zugangscode eingeben.</p>
<input id="c" type="password" placeholder="Zugangscode" autofocus>
<button onclick="document.cookie='psp_radar_code='+encodeURIComponent(c.value)+
';path=/;max-age=2592000;SameSite=Strict';location.reload()">Weiter</button>
</div><script>c.addEventListener('keydown',e=>{if(e.key==='Enter')
document.querySelector('button').click()})</script></body></html>"""
