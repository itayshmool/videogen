"""Tests for data models."""

from pathlib import Path

import pytest

from videogen.models import (
    BrowseResult,
    KenBurnsDirection,
    Scene,
    TransitionType,
    VideoConfig,
    VideoScript,
)


class TestVideoConfig:
    def test_defaults(self):
        config = VideoConfig()
        assert config.width == 1080
        assert config.height == 1920
        assert config.fps == 30
        assert config.scene_duration == 4.0
        assert config.transition_duration == 0.5
        assert config.max_scenes == 5

    def test_custom_values(self):
        config = VideoConfig(width=720, height=1280, fps=24, max_scenes=3)
        assert config.width == 720
        assert config.max_scenes == 3


class TestScene:
    def test_defaults(self):
        scene = Scene(screenshot_path=Path("/tmp/test.png"))
        assert scene.headline == ""
        assert scene.subtext == ""
        assert scene.duration == 4.0
        assert scene.transition == TransitionType.CROSSFADE
        assert scene.ken_burns == KenBurnsDirection.ZOOM_IN


class TestVideoScript:
    def test_empty_scenes(self):
        script = VideoScript(product_name="Test", hook="Hook")
        assert script.scenes == []
        assert script.cta == "Learn more"

    def test_with_scenes(self):
        script = VideoScript(
            product_name="Test",
            hook="Hook",
            scenes=[Scene(screenshot_path=Path("/tmp/a.png"))],
            cta="Buy now",
        )
        assert len(script.scenes) == 1
        assert script.cta == "Buy now"


class TestBrowseResult:
    def test_defaults(self):
        result = BrowseResult()
        assert result.product_name == ""
        assert result.screenshots == []
        assert result.features == []

    def test_with_data(self):
        result = BrowseResult(
            product_name="Foo",
            tagline="Bar",
            features=["a", "b"],
            screenshots=[Path("/tmp/1.png")],
            url="https://example.com",
        )
        assert result.product_name == "Foo"
        assert len(result.screenshots) == 1
