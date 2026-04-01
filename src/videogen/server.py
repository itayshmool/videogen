"""FastAPI server wrapping the videogen pipeline with real-time log streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import re

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from videogen.config import OUTPUT_DIR, RUNS_DIR

app = FastAPI(title="videogen")

# Ensure directories exist for static mounts
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/files/runs", StaticFiles(directory=str(RUNS_DIR)), name="runs")

# Track running jobs
_jobs: dict[str, dict] = {}


class _SSELogHandler(logging.Handler):
    """Captures log records into an asyncio queue for SSE streaming."""

    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord):
        try:
            self.queue.put_nowait({
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
            })
        except asyncio.QueueFull:
            pass


@app.get("/", response_class=HTMLResponse)
async def index():
    ui_path = Path(__file__).parent.parent.parent / "ui" / "index.html"
    return FileResponse(ui_path, media_type="text/html")


# ---------------------------------------------------------------------------
# Runs API
# ---------------------------------------------------------------------------


@app.get("/api/runs")
async def list_runs():
    """List all runs, newest first."""
    runs = []
    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            manifest_path = run_dir / "run.json"
            if manifest_path.exists():
                try:
                    runs.append(json.loads(manifest_path.read_text()))
                except (json.JSONDecodeError, OSError):
                    continue
    return runs


_RUN_ID_RE = re.compile(r"^[\w\-]+$")


def _valid_run_id(run_id: str) -> bool:
    """Reject path-traversal attempts (e.g. '../', '/')."""
    return bool(_RUN_ID_RE.match(run_id))


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Get a single run's manifest."""
    if not _valid_run_id(run_id):
        return {"error": "Invalid run ID"}
    manifest_path = RUNS_DIR / run_id / "run.json"
    if not manifest_path.exists():
        return {"error": "Run not found"}
    return json.loads(manifest_path.read_text())


@app.get("/api/runs/{run_id}/screenshots")
async def run_screenshots(run_id: str):
    """List screenshots for a specific run."""
    if not _valid_run_id(run_id):
        return {"error": "Invalid run ID"}
    screenshots_dir = RUNS_DIR / run_id / "screenshots"
    shots = []
    if screenshots_dir.exists():
        for f in sorted(screenshots_dir.glob("*.png")):
            shots.append({
                "name": f.name,
                "url": f"/files/runs/{run_id}/screenshots/{f.name}",
            })
    return shots


@app.get("/api/runs/{run_id}/video")
async def run_video(run_id: str):
    """Get the video info for a specific run."""
    if not _valid_run_id(run_id):
        return {"error": "Invalid run ID"}
    run_dir = RUNS_DIR / run_id
    videos = list(run_dir.glob("*.mp4"))
    if not videos:
        return {"error": "No video found"}
    v = videos[0]
    return {
        "name": v.name,
        "url": f"/files/runs/{run_id}/{v.name}",
        "size": v.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Legacy endpoints (backward compat)
# ---------------------------------------------------------------------------


@app.get("/api/videos")
async def list_videos():
    """List all generated videos across runs and legacy output."""
    videos = []
    # Legacy flat videos
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            videos.append({
                "name": f.name,
                "size": f.stat().st_size,
                "url": f"/files/output/{f.name}",
                "modified": f.stat().st_mtime,
            })
    # Run-based videos
    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            for f in run_dir.glob("*.mp4"):
                videos.append({
                    "name": f"{run_dir.name}/{f.name}",
                    "size": f.stat().st_size,
                    "url": f"/files/runs/{run_dir.name}/{f.name}",
                    "modified": f.stat().st_mtime,
                    "run_id": run_dir.name,
                })
    return videos


@app.get("/api/screenshots")
async def list_screenshots():
    """List screenshots from the latest run (backward compat)."""
    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            shots_dir = run_dir / "screenshots"
            if shots_dir.exists() and any(shots_dir.glob("*.png")):
                shots = []
                for f in sorted(shots_dir.glob("*.png")):
                    shots.append({
                        "name": f.name,
                        "url": f"/files/runs/{run_dir.name}/screenshots/{f.name}",
                    })
                return shots
    return []


# ---------------------------------------------------------------------------
# Jobs / Generation
# ---------------------------------------------------------------------------


@app.post("/api/generate")
async def start_generate(request: Request):
    """Start a video generation job, returns job ID."""
    body = await request.json()
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "running", "output": None, "error": None, "run_id": None}

    asyncio.create_task(_run_job(job_id, body))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Check job status."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    return {k: v for k, v in job.items() if k != "_queue"}


@app.get("/api/jobs/{job_id}/logs")
async def job_logs(job_id: str):
    """Stream logs for a job via SSE."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}

    queue = job.get("_queue")
    if not queue:
        return {"error": "No log stream"}

    async def event_stream():
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield f"data: {json.dumps(entry)}\n\n"
                if entry.get("_done"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'_ping': True})}\n\n"
                job_data = _jobs.get(job_id, {})
                if job_data.get("status") != "running":
                    break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_job(job_id: str, params: dict):
    """Run the pipeline in background, streaming logs to SSE queue."""
    from videogen.cli import _run_pipeline
    from videogen.config import PROFILE_DIR

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _jobs[job_id]["run_id"] = run_id

    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _jobs[job_id]["_queue"] = queue

    # Attach log handler
    handler = _SSELogHandler(queue)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        output_path = await _run_pipeline(
            url=params["url"],
            max_scenes=params.get("scenes", 5),
            scene_duration=params.get("duration", 4.0),
            music=Path(params["music"]) if params.get("music") else None,
            output_dir=OUTPUT_DIR,
            headless=params.get("headless", True),
            login=params.get("login", False),
            profile_dir=Path(params.get("profile_dir", str(PROFILE_DIR))),
            login_url=params.get("login_url"),
            username=params.get("username"),
            password=params.get("password"),
            custom_task=params.get("task"),
            landscape=params.get("landscape", False),
            run_id=run_id,
        )
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["output"] = f"/files/runs/{run_id}/video.mp4"
        queue.put_nowait({"level": "INFO", "message": f"Video saved: {output_path.name}", "_done": True})
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        queue.put_nowait({"level": "ERROR", "message": str(e), "_done": True})
    finally:
        root_logger.removeHandler(handler)
