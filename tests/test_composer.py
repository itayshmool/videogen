"""Tests for the composer module — FFmpeg video assembly."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from videogen.composer import _ken_burns_filter, compose_video
from videogen.models import KenBurnsDirection, Scene, VideoConfig, VideoScript


# ---------------------------------------------------------------------------
# Ken Burns filter generation
# ---------------------------------------------------------------------------


class TestKenBurnsFilter:
    def test_zoom_in_filter(self):
        f = _ken_burns_filter(KenBurnsDirection.ZOOM_IN, 1080, 1920, 4.0)
        assert "zoompan" in f
        assert "1080x1920" in f
        assert "min(zoom+0.0015,1.15)" in f

    def test_zoom_out_filter(self):
        f = _ken_burns_filter(KenBurnsDirection.ZOOM_OUT, 1080, 1920, 4.0)
        assert "zoompan" in f
        assert "max(zoom-0.0015,1.0)" in f

    def test_pan_left_filter(self):
        f = _ken_burns_filter(KenBurnsDirection.PAN_LEFT, 1080, 1920, 3.0)
        assert "zoompan" in f
        assert "max(x-1,0)" in f

    def test_pan_right_filter(self):
        f = _ken_burns_filter(KenBurnsDirection.PAN_RIGHT, 1080, 1920, 3.0)
        assert "zoompan" in f
        assert "min(x+1,iw/4)" in f

    def test_duration_affects_frame_count(self):
        short = _ken_burns_filter(KenBurnsDirection.ZOOM_IN, 1080, 1920, 2.0)
        long = _ken_burns_filter(KenBurnsDirection.ZOOM_IN, 1080, 1920, 8.0)
        # d= value should differ
        assert "d=50" in short
        assert "d=200" in long


# ---------------------------------------------------------------------------
# compose_video — end-to-end with real FFmpeg
# ---------------------------------------------------------------------------


@pytest.fixture
def video_fixtures(tmp_path):
    """Create minimal test frames and a script for video composition."""
    frames = []
    for i, color in enumerate(["red", "blue", "green"]):
        p = tmp_path / f"frame_{i}.png"
        Image.new("RGB", (1080, 1920), color=color).save(p)
        frames.append(p)

    script = VideoScript(
        product_name="TestProduct",
        hook="Hook text",
        scenes=[
            Scene(
                screenshot_path=frames[1],
                headline="Scene 1",
                duration=2.0,
                ken_burns=KenBurnsDirection.ZOOM_IN,
            ),
        ],
        cta="Try it",
    )

    config = VideoConfig(output_dir=tmp_path / "output", fps=15)

    return frames, script, config


class TestComposeVideo:
    @pytest.mark.slow
    def test_produces_mp4_file(self, video_fixtures):
        frames, script, config = video_fixtures
        output = compose_video(script, frames, config)

        assert output.exists()
        assert output.suffix == ".mp4"
        assert output.stat().st_size > 0

    @pytest.mark.slow
    def test_output_is_valid_video(self, video_fixtures):
        """Verify FFmpeg can probe the output file."""
        frames, script, config = video_fixtures
        output = compose_video(script, frames, config)

        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", str(output)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "1080,1920" in result.stdout

    @pytest.mark.slow
    def test_single_frame_produces_video(self, tmp_path):
        """Even a single scene should produce a valid video."""
        frame = tmp_path / "single.png"
        Image.new("RGB", (1080, 1920), color="white").save(frame)

        script = VideoScript(
            product_name="Solo",
            hook="Hook",
            scenes=[],
            cta="CTA",
        )
        config = VideoConfig(output_dir=tmp_path / "output", fps=15)

        # Just hook + cta = 1 frame won't work with xfade, but let's test
        # Actually we need hook frame path to be the only one
        output = compose_video(script, [frame], config)
        assert output.exists()
