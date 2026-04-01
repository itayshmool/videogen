from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class TransitionType(str, Enum):
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"
    SLIDE_LEFT = "slide_left"


class KenBurnsDirection(str, Enum):
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"


class Scene(BaseModel):
    screenshot_path: Path
    headline: str = ""
    subtext: str = ""
    duration: float = 4.0
    transition: TransitionType = TransitionType.CROSSFADE
    ken_burns: KenBurnsDirection = KenBurnsDirection.ZOOM_IN


class VideoScript(BaseModel):
    product_name: str
    hook: str = Field(description="Attention-grabbing text for the first 3 seconds")
    scenes: list[Scene] = Field(default_factory=list)
    cta: str = Field(default="Learn more", description="Call-to-action text for the final scene")


class VideoConfig(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    scene_duration: float = 4.0
    transition_duration: float = 0.5
    max_scenes: int = 5
    output_dir: Path = Path("output")
    font_path: Path | None = None
    music_path: Path | None = None
    crop: bool = True


class BrowseResult(BaseModel):
    product_name: str = ""
    tagline: str = ""
    features: list[str] = Field(default_factory=list)
    screenshots: list[Path] = Field(default_factory=list)
    url: str = ""


class RunStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class RunManifest(BaseModel):
    run_id: str
    url: str
    status: RunStatus = RunStatus.RUNNING
    created_at: str
    finished_at: str | None = None
    config: dict = Field(default_factory=dict)
    product_name: str = ""
    hook: str = ""
    cta: str = ""
    scenes_count: int = 0
    error: str | None = None
