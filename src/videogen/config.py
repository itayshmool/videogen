from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = PROJECT_ROOT / "output"
RUNS_DIR = OUTPUT_DIR / "runs"
TMP_DIR = PROJECT_ROOT / ".tmp"
PROFILE_DIR = PROJECT_ROOT / ".browser-profile"


def create_run_dir(run_id: str | None = None) -> Path:
    """Create and return a new run directory under output/runs/."""
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    (run_dir / "frames").mkdir(parents=True, exist_ok=True)
    return run_dir
