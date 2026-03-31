"""FastAPI server wrapping the videogen pipeline with real-time log streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from videogen.config import OUTPUT_DIR, TMP_DIR

app = FastAPI(title="videogen")

# Mount output dir for serving generated videos and screenshots
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

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


@app.get("/api/videos")
async def list_videos():
    """List all generated videos."""
    videos = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            videos.append({
                "name": f.name,
                "size": f.stat().st_size,
                "url": f"/files/output/{f.name}",
                "modified": f.stat().st_mtime,
            })
    return videos


@app.get("/api/screenshots")
async def list_screenshots():
    """List captured screenshots from last run."""
    shots = []
    screenshots_dir = TMP_DIR / "screenshots"
    if screenshots_dir.exists():
        for f in sorted(screenshots_dir.glob("*.png")):
            shots.append({
                "name": f.name,
                "url": f"/files/tmp/screenshots/{f.name}",
            })
    return shots


@app.post("/api/generate")
async def start_generate(request: Request):
    """Start a video generation job, returns job ID."""
    body = await request.json()
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "running", "output": None, "error": None}

    asyncio.create_task(_run_job(job_id, body))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Check job status."""
    job = _jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


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
            keep_tmp=True,
            profile_dir=Path(params.get("profile_dir", str(PROFILE_DIR))),
            login_url=params.get("login_url"),
            username=params.get("username"),
            password=params.get("password"),
            custom_task=params.get("task"),
            landscape=params.get("landscape", False),
        )
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["output"] = f"/files/output/{output_path.name}"
        queue.put_nowait({"level": "INFO", "message": f"Video saved: {output_path.name}", "_done": True})
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        queue.put_nowait({"level": "ERROR", "message": str(e), "_done": True})
    finally:
        root_logger.removeHandler(handler)


def _mount_tmp():
    """Mount tmp directory if it exists (for screenshots)."""
    tmp_screenshots = TMP_DIR / "screenshots"
    tmp_screenshots.mkdir(parents=True, exist_ok=True)
    app.mount("/files/tmp/screenshots", StaticFiles(directory=str(tmp_screenshots)), name="screenshots")
    tmp_frames = TMP_DIR / "frames"
    tmp_frames.mkdir(parents=True, exist_ok=True)
    app.mount("/files/tmp/frames", StaticFiles(directory=str(tmp_frames)), name="frames")


_mount_tmp()
