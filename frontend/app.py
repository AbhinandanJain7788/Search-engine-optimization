"""Claude SEO frontend server.

FastAPI app:
- Serves static SPA at /
- POST /api/audit  -> start a job (returns job_id)
- GET  /api/jobs/{id}/stream -> SSE stream of progress events
- POST /api/jobs/{id}/stop -> request cancellation
- GET  /api/jobs/{id}/summary -> final summary JSON
- GET  /api/jobs/{id}/report.pdf -> download PDF
- GET  /api/jobs/{id}/report.md -> download markdown
- GET  /api/commands -> command catalog
- GET  /api/agents -> agent catalog
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                                StreamingResponse)
from fastapi.staticfiles import StaticFiles

import audit_runner
from commands import COMMANDS, AGENTS

ROOT = pathlib.Path(__file__).parent
RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)
STATIC = ROOT / "static"

app = FastAPI(title="Claude SEO Frontend")

# In-memory job registry
JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()


@app.get("/api/commands")
def get_commands():
    return {"commands": COMMANDS}


@app.get("/api/agents")
def get_agents():
    return {"agents": AGENTS}


@app.post("/api/audit")
async def start_audit(payload: dict = Body(...)):
    url = (payload.get("url") or "").strip()
    command = (payload.get("command") or "audit").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")

    job_id = uuid.uuid4().hex[:12]
    job_dir = RUNS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    state = audit_runner.AuditState()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    job = {
        "id": job_id, "url": url, "command": command,
        "state": state, "queue": queue, "dir": str(job_dir),
        "started_at": time.time(), "status": "running",
        "loop": loop,
    }

    with LOCK:
        JOBS[job_id] = job

    def on_event(ev: dict):
        # Called from worker thread; safely enqueue into asyncio queue.
        try:
            loop.call_soon_threadsafe(queue.put_nowait, ev)
        except RuntimeError:
            # Loop closed; drop
            pass

    def worker():
        try:
            audit_runner.run_audit(url, command, job_dir, state, on_event)
            with LOCK:
                JOBS[job_id]["status"] = "done"
        except Exception as exc:
            err_event = {"agent": "orchestrator", "status": "error",
                         "msg": f"{type(exc).__name__}: {exc}",
                         "ts": time.time()}
            state.events.append(err_event)
            try:
                loop.call_soon_threadsafe(queue.put_nowait, err_event)
            except RuntimeError:
                pass
            with LOCK:
                JOBS[job_id]["status"] = ("cancelled"
                                          if state.cancelled else "error")
        finally:
            try:
                loop.call_soon_threadsafe(queue.put_nowait,
                                          {"_terminal": True})
            except RuntimeError:
                pass

    threading.Thread(target=worker, daemon=True, name=f"audit-{job_id}").start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/stream")
async def stream(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    queue: asyncio.Queue = job["queue"]

    async def gen():
        # Replay any events already captured (so a slow client doesn't miss the start).
        for ev in list(job["state"].events):
            yield f"data: {json.dumps(ev)}\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if isinstance(ev, dict) and ev.get("_terminal"):
                with LOCK:
                    final_status = JOBS[job_id]["status"]
                yield f"data: {json.dumps({'_terminal': True, 'status': final_status})}\n\n"
                break
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job["state"].cancelled = True
    return {"ok": True, "status": "cancelling"}


@app.get("/api/jobs/{job_id}/summary")
def job_summary(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    summary_path = pathlib.Path(job["dir"]) / "summary.json"
    if summary_path.exists():
        return JSONResponse(json.loads(summary_path.read_text(encoding="utf-8")))
    return {"status": job["status"]}


@app.get("/api/jobs/{job_id}/report.pdf")
def job_pdf(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    pdf = pathlib.Path(job["dir"]) / "report.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="report not ready")
    safe_host = job["url"].replace("https://", "").replace("http://", "")
    safe_host = "".join(c for c in safe_host if c.isalnum() or c in "-_.")[:40]
    return FileResponse(pdf, media_type="application/pdf",
                         filename=f"seo-audit-{safe_host}.pdf")


@app.get("/api/jobs/{job_id}/report.md")
def job_md(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    md = pathlib.Path(job["dir"]) / "report.md"
    if not md.exists():
        raise HTTPException(status_code=404, detail="report not ready")
    return FileResponse(md, media_type="text/markdown",
                         filename=f"seo-audit-{job_id}.md")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
