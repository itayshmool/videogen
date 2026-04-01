from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from videogen.models import KenBurnsDirection, VideoConfig, VideoScript

logger = logging.getLogger(__name__)


def _ken_burns_filter(direction: KenBurnsDirection, w: int, h: int, duration: float) -> str:
    """Generate an FFmpeg zoompan filter string for Ken Burns effect."""
    # zoompan: zoom from 1.0->1.15 (or reverse), with slow pan
    frames = int(duration * 25)  # zoompan uses its own fps
    out_frames = int(duration * 25)

    if direction == KenBurnsDirection.ZOOM_IN:
        return f"zoompan=z='min(zoom+0.0015,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps=25"
    elif direction == KenBurnsDirection.ZOOM_OUT:
        return f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0015,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps=25"
    elif direction == KenBurnsDirection.PAN_LEFT:
        return f"zoompan=z='1.10':x='if(eq(on,1),iw/4,max(x-1,0))':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps=25"
    else:  # PAN_RIGHT
        return f"zoompan=z='1.10':x='if(eq(on,1),0,min(x+1,iw/4))':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps=25"


def compose_video(
    script: VideoScript,
    frame_paths: list[Path],
    config: VideoConfig,
    output_name: str | None = None,
) -> Path:
    """Assemble frame images into a final MP4 video with Ken Burns + transitions.

    Uses a two-pass approach:
    1. Generate individual scene clips with Ken Burns effect
    2. Concatenate with crossfade transitions
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    if output_name is None:
        output_name = "video.mp4"

    output_path = config.output_dir / output_name
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Build durations list: hook + scenes + cta
    durations: list[float] = [3.0]  # hook duration
    ken_burns_dirs: list[KenBurnsDirection] = [KenBurnsDirection.ZOOM_IN]  # hook

    for scene in script.scenes:
        durations.append(scene.duration)
        ken_burns_dirs.append(scene.ken_burns)

    durations.append(3.0)  # cta duration
    ken_burns_dirs.append(KenBurnsDirection.ZOOM_OUT)  # cta

    # Step 1: Generate individual clips with Ken Burns
    clip_paths: list[Path] = []
    for i, (frame_path, duration, kb_dir) in enumerate(zip(frame_paths, durations, ken_burns_dirs)):
        clip_path = frame_path.parent / f"clip_{i:02d}.mp4"
        clip_paths.append(clip_path)

        kb_filter = _ken_burns_filter(kb_dir, config.width, config.height, duration)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(frame_path),
            "-vf", f"{kb_filter},fps={config.fps},format=yuv420p",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(clip_path),
        ]
        logger.info("Generating clip %d/%d: %s", i + 1, len(frame_paths), clip_path.name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg clip error: %s", result.stderr[-500:] if result.stderr else "unknown")
            raise RuntimeError(f"FFmpeg failed for clip {i}: {result.stderr[-300:]}")

    # Step 2: Concatenate clips with crossfade transitions
    if len(clip_paths) == 1:
        # Single clip — just copy
        clip_paths[0].rename(output_path)
    else:
        output_path = _concat_with_xfade(clip_paths, durations, config, output_path)

    # Step 3: Add background music if provided
    if config.music_path and config.music_path.exists():
        output_path = _add_music(output_path, config.music_path)

    logger.info("Video saved: %s", output_path)
    return output_path


def _concat_with_xfade(
    clip_paths: list[Path],
    durations: list[float],
    config: VideoConfig,
    output_path: Path,
) -> Path:
    """Concatenate clips using FFmpeg xfade filter for crossfade transitions."""
    xfade_dur = config.transition_duration

    # Build complex filter graph
    # Each xfade takes two inputs and produces one output
    # offset = cumulative duration minus transition overlap
    filter_parts: list[str] = []
    offsets: list[float] = []

    cumulative = 0.0
    for i in range(len(clip_paths) - 1):
        offset = cumulative + durations[i] - xfade_dur
        offsets.append(offset)
        cumulative = offset  # next clip starts at the xfade point

        if i == 0:
            in1 = "[0:v]"
            in2 = "[1:v]"
        else:
            in1 = f"[v{i}]"
            in2 = f"[{i + 1}:v]"

        if i == len(clip_paths) - 2:
            out = "[vout]"
        else:
            out = f"[v{i + 1}]"

        filter_parts.append(
            f"{in1}{in2}xfade=transition=fade:duration={xfade_dur}:offset={offset:.2f}{out}"
        )

    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y"]
    for clip in clip_paths:
        cmd.extend(["-i", str(clip)])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ])

    logger.info("Concatenating %d clips with crossfade", len(clip_paths))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg concat error: %s", result.stderr[-500:] if result.stderr else "unknown")
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-300:]}")

    return output_path


def _add_music(video_path: Path, music_path: Path) -> Path:
    """Overlay background music on the video, fading out at the end."""
    out = video_path.with_name(video_path.stem + "_music" + video_path.suffix)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex",
        "[1:a]afade=t=in:st=0:d=1,afade=t=out:st=-2:d=2,volume=0.3[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-shortest",
        str(out),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("Music overlay failed, returning video without music: %s", result.stderr[-200:])
        return video_path

    # Replace original with music version
    video_path.unlink()
    out.rename(video_path)
    return video_path
