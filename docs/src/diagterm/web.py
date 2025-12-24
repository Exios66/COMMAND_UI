from __future__ import annotations

import os
from pathlib import Path
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
    allow_methods=["*"],
    allow_headers=["*"],
)

_power = PowerReader()


def _find_site_dir() -> Path:
    """Find the static site directory containing dist/index.html.

    Supports these layouts:
    - repo-root/docs/dist (preferred)
    - repo-root/web/dist (legacy)
    - package located at docs/src/diagterm or src/diagterm
    """
    here = Path(__file__).resolve()

    # Walk up a few levels and probe common locations.
    for p in list(here.parents)[:8]:
        # If we're inside docs/ already
        if (p / "dist" / "index.html").exists():
            return p
        # Typical repo root
        if (p / "docs" / "dist" / "index.html").exists():
            return p / "docs"
        if (p / "web" / "dist" / "index.html").exists():
            return p / "web"

    # Fallback: default to repo-root/docs even if dist doesn't exist yet
    for p in list(here.parents)[:8]:
        if (p / "docs").exists():
            return p / "docs"
    return here.parent


_site_dir = _find_site_dir()
_dist_dir = _site_dir / "dist"


# API Routes (must be defined before static file routes)
@app.get("/api/capabilities")
def api_capabilities() -> dict:
    """Return backend capabilities for permission management."""
    return {
        "version": "0.1.0",
        "runner_enabled": os.environ.get("DIAGTERM_WEB_ENABLE_RUNNER", "0") == "1",
        "diagnostics_enabled": True,
        "services_enabled": True,
    }


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


# Static file serving and SPA routing
if _dist_dir.exists() and (_dist_dir / "index.html").exists():
    # Serve static assets (JS, CSS, etc.)
    if (_dist_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_dist_dir / "assets")), name="assets")
    
    # Serve root index.html
    @app.get("/")
    async def root():
        index_path = _dist_dir / "index.html"
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    # Serve other static files from dist root (favicons, manifest, etc.)
    @app.get("/{filename}")
    async def serve_static(filename: str, request: Request):
        # Don't interfere with API routes
        if filename.startswith("api"):
            raise HTTPException(status_code=404, detail="Not Found")
        
        filepath = _dist_dir / filename
        if filepath.exists() and filepath.is_file():
            return FileResponse(str(filepath))
        
        # For SPA routing, serve index.html for any non-API, non-file route
        index_path = _dist_dir / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        
        raise HTTPException(status_code=404, detail="Not Found")
else:
    # If dist doesn't exist, provide helpful error message
    @app.get("/")
    async def root():
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>DiagTerm Web - Frontend Not Built</title>
                <style>
                    body {{
                        font-family: system-ui, sans-serif;
                        max-width: 600px;
                        margin: 50px auto;
                        padding: 20px;
                        background: #0b1220;
                        color: #e6ecff;
                    }}
                    h1 {{ color: #7aa2ff; }}
                    code {{
                        background: #111a2e;
                        padding: 2px 6px;
                        border-radius: 3px;
                        color: #a8b3d6;
                    }}
                    .box {{
                        background: #111a2e;
                        border: 1px solid #24304f;
                        padding: 20px;
                        border-radius: 8px;
                        margin-top: 20px;
                    }}
                    pre {{
                        background: #111a2e;
                        padding: 12px;
                        border-radius: 4px;
                        overflow-x: auto;
                    }}
                </style>
            </head>
            <body>
                <h1>Frontend Not Built</h1>
                <div class="box">
                    <p>The React frontend has not been built yet.</p>
                    <p>To build it, run:</p>
                    <pre><code>cd docs
npm install
npm run build</code></pre>
                    <p>Or for development with hot reload:</p>
                    <pre><code>cd docs
npm install
npm run dev</code></pre>
                    <p><small>Expected directory: <code>{_dist_dir}</code></small></p>
                </div>
                <div class="box">
                    <h2>API Endpoints</h2>
                    <p>The API is available at:</p>
                    <ul>
                        <li><code>GET /api/summary</code> - System summary</li>
                        <li><code>GET /api/processes?limit=25</code> - Top processes</li>
                        <li><code>GET /api/services?limit=25</code> - Running services</li>
                        <li><code>GET /api/diagnostics?limit=120</code> - Diagnostics feed</li>
                        <li><code>POST /api/run</code> - Run command (requires DIAGTERM_WEB_ENABLE_RUNNER=1)</li>
                    </ul>
                </div>
            </body>
            </html>
            """,
            status_code=503
        )


def main() -> None:
    """Run the web API server."""
    import uvicorn

    host = os.environ.get("DIAGTERM_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("DIAGTERM_WEB_PORT", "8765"))
    uvicorn.run("diagterm.web:app", host=host, port=port, reload=False)