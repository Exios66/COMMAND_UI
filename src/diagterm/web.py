from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from diagterm.collectors import (
    PowerReader,
    get_recent_diagnostics,
    get_running_services,
    get_system_summary,
    get_top_processes,
)
from diagterm.executor import run_shell_command


class RunRequest(BaseModel):
    cmd: str
    timeout_s: float = 120.0


app = FastAPI(title="diagterm-web", version="0.1.0")

# Dev-friendly defaults: allow local Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

_power = PowerReader()


@app.get("/api/summary")
def api_summary() -> dict:
    return asdict(get_system_summary(_power))


@app.get("/api/processes")
def api_processes(limit: int = 25) -> dict:
    rows = get_top_processes(limit=min(max(int(limit), 1), 200))
    return {"processes": [asdict(r) for r in rows]}


@app.get("/api/services")
def api_services(limit: int = 25) -> dict:
    rows = get_running_services(limit=min(max(int(limit), 1), 200))
    return {"services": [asdict(r) for r in rows]}


@app.get("/api/diagnostics")
def api_diagnostics(limit: int = 120) -> dict:
    lines = get_recent_diagnostics(limit=min(max(int(limit), 1), 2000))
    return {"lines": lines}


@app.post("/api/run")
async def api_run(req: RunRequest) -> dict:
    # SECURITY: disabled by default.
    # Enable explicitly with DIAGTERM_WEB_ENABLE_RUNNER=1
    if os.environ.get("DIAGTERM_WEB_ENABLE_RUNNER", "0") != "1":
        raise HTTPException(status_code=403, detail="Command runner disabled (set DIAGTERM_WEB_ENABLE_RUNNER=1 to enable)")

    cmd = (req.cmd or "").strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="cmd is required")

    timeout_s = float(req.timeout_s)
    if timeout_s <= 0:
        timeout_s = 120.0

    res = await run_shell_command(cmd, timeout_s=timeout_s)
    return {
        "cmd": res.cmd,
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }


def main() -> None:
    """Run the web API server."""
    import uvicorn

    host = os.environ.get("DIAGTERM_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DIAGTERM_WEB_PORT", "8765"))
    uvicorn.run("diagterm.web:app", host=host, port=port, reload=False)
