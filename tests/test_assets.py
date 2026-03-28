"""Tests for the assets module — image processing pipeline."""

from pathlib import Path

import pytest
from PIL import Image

from videogen.assets import (
    create_cta_frame,
    create_hook_frame,
    create_scene_frame,
    crop_to_vertical,
    prepare_assets,
)
from videogen.models import KenBurnsDirection, Scene, VideoConfig, VideoScript


@pytest.fixture
def config():
    return VideoConfig()


@pytest.fixture
def wide_image():
    """A landscape image wider than 9:16."""
    return Image.new("RGB", (1920, 1080), color="blue")


@pytest.fixture
def tall_image():
    """A portrait image taller than 9:16."""
    return Image.new("RGB", (400, 2000), color="green")


@pytest.fixture
def square_image():
    return Image.new("RGB", (1000, 1000), color="red")


# ---------------------------------------------------------------------------
# crop_to_vertical
# ---------------------------------------------------------------------------


class TestCropToVertical:
    def test_output_dimensions(self, wide_image, config):
        result = crop_to_vertical(wide_image, config.width, config.height)
        assert result.size == (1080, 1920)

    def test_wide_image_crops_sides(self, wide_image, config):
        """Landscape image should be cropped on sides to fit 9:16."""
        result = crop_to_vertical(wide_image, config.width, config.height)
        assert result.size == (config.width, config.height)

    def test_tall_image_crops_bottom(self, tall_image, config):
        """Very tall image should be cropped, keeping the top."""
        result = crop_to_vertical(tall_image, config.width, config.height)
        assert result.size == (config.width, config.height)

    def test_square_image(self, square_image, config):
        result = crop_to_vertical(square_image, config.width, config.height)
        assert result.size == (config.width, config.height)

    def test_already_correct_ratio(self, config):
        """Image already at 9:16 should still resize to exact dimensions."""
        img = Image.new("RGB", (540, 960), color="yellow")
        result = crop_to_vertical(img, config.width, config.height)
        assert result.size == (1080, 1920)


# ---------------------------------------------------------------------------
# Frame generators
# ---------------------------------------------------------------------------


class TestCreateHookFrame:
    def test_dimensions(self, config):
        img = create_hook_frame("HOOK TEXT", config)
        assert img.size == (1080, 1920)

    def test_mode_is_rgb(self, config):
        img = create_hook_frame("HOOK TEXT", config)
        assert img.mode == "RGB"

    def test_empty_text(self, config):
        """Empty hook text should not crash."""
        img = create_hook_frame("", config)
        assert img.size == (1080, 1920)


class TestCreateCtaFrame:
    def test_dimensions(self, config):
        img = create_cta_frame("TRY IT NOW", "MyProduct", config)
        assert img.size == (1080, 1920)

    def test_empty_product_name(self, config):
        img = create_cta_frame("CTA", "", config)
        assert img.size == (1080, 1920)


class TestCreateSceneFrame:
    def test_dimensions(self, config, tmp_path):
        # Create a test screenshot
        screenshot = tmp_path / "test.png"
        Image.new("RGB", (1920, 1080), color="purple").save(screenshot)

        img = create_scene_frame(screenshot, "Headline", "Subtext", config)
        assert img.size == (1080, 1920)
        assert img.mode == "RGB"

    def test_no_text_overlay(self, config, tmp_path):
        screenshot = tmp_path / "test.png"
        Image.new("RGB", (1920, 1080), color="purple").save(screenshot)

        img = create_scene_frame(screenshot, "", "", config)
        assert img.size == (1080, 1920)


# ---------------------------------------------------------------------------
# prepare_assets
# ---------------------------------------------------------------------------


class TestPrepareAssets:
    def test_returns_correct_number_of_frames(self, config, tmp_path):
        # Create fake screenshots
        screenshots = []
        for i in range(3):
            p = tmp_path / f"shot_{i}.png"
            Image.new("RGB", (1920, 1080), color="gray").save(p)
            screenshots.append(p)

        script = VideoScript(
            product_name="Test",
            hook="Hook text",
            scenes=[
                Scene(screenshot_path=screenshots[0], headline="H1", subtext="S1"),
                Scene(screenshot_path=screenshots[1], headline="H2", subtext="S2"),
                Scene(screenshot_path=screenshots[2], headline="H3", subtext="S3"),
            ],
            cta="Try it",
        )

        frames = prepare_assets(script, config)
        # 1 hook + 3 scenes + 1 cta = 5 frames
        assert len(frames) == 5

    def test_all_frames_are_valid_pngs(self, config, tmp_path):
        p = tmp_path / "shot.png"
        Image.new("RGB", (1920, 1080)).save(p)

        script = VideoScript(
            product_name="Test",
            hook="Hook",
            scenes=[Scene(screenshot_path=p, headline="H")],
            cta="CTA",
        )

        frames = prepare_assets(script, config)
        for frame_path in frames:
            assert frame_path.exists()
            img = Image.open(frame_path)
            assert img.size == (1080, 1920)

    def test_hook_is_first_cta_is_last(self, config, tmp_path):
        p = tmp_path / "shot.png"
        Image.new("RGB", (1920, 1080)).save(p)

        script = VideoScript(
            product_name="Test",
            hook="Hook",
            scenes=[Scene(screenshot_path=p, headline="H")],
            cta="CTA",
        )

        frames = prepare_assets(script, config)
        assert "hook" in frames[0].name
        assert "cta" in frames[-1].name
