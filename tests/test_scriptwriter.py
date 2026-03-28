"""Tests for the scriptwriter module — Gemini script generation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videogen.models import BrowseResult, VideoConfig
from videogen.scriptwriter import generate_script


@pytest.fixture
def browse_result(tmp_path):
    """A minimal BrowseResult with fake screenshots."""
    screenshots = []
    for i in range(3):
        p = tmp_path / f"shot_{i}.png"
        p.write_bytes(b"fake png")
        screenshots.append(p)

    return BrowseResult(
        product_name="TestProduct",
        tagline="The best product",
        features=["Fast", "Easy", "Reliable"],
        screenshots=screenshots,
        url="https://example.com",
    )


@pytest.fixture
def config():
    return VideoConfig(max_scenes=3)


def _mock_gemini_response(data: dict) -> MagicMock:
    """Create a mock Gemini response object."""
    response = MagicMock()
    response.text = json.dumps(data)
    return response


class TestGenerateScript:
    @pytest.mark.asyncio
    async def test_returns_video_script_with_scenes(self, browse_result, config):
        """Should return a VideoScript with the correct number of scenes."""
        llm_output = {
            "product_name": "TestProduct",
            "hook": "Stop wasting time!",
            "scenes": [
                {"screenshot_index": 0, "headline": "Fast", "subtext": "Really fast", "duration": 4, "transition": "crossfade", "ken_burns": "zoom_in"},
                {"screenshot_index": 1, "headline": "Easy", "subtext": "So easy", "duration": 3, "transition": "fade_black", "ken_burns": "pan_left"},
                {"screenshot_index": 2, "headline": "Reliable", "subtext": "", "duration": 4, "transition": "crossfade", "ken_burns": "zoom_out"},
            ],
            "cta": "Try it free",
        }

        with patch("videogen.scriptwriter.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=_mock_gemini_response(llm_output)
            )
            mock_genai.Client.return_value = mock_client

            with patch.dict("os.environ", {"GOOGLE_API_KEY": "fake-key"}):
                script = await generate_script(browse_result, config)

        assert script.product_name == "TestProduct"
        assert script.hook == "Stop wasting time!"
        assert len(script.scenes) == 3
        assert script.cta == "Try it free"

    @pytest.mark.asyncio
    async def test_screenshot_index_clamped(self, browse_result, config):
        """Screenshot index beyond range should be clamped to max."""
        llm_output = {
            "product_name": "Test",
            "hook": "Hook",
            "scenes": [
                {"screenshot_index": 99, "headline": "H", "duration": 3, "transition": "crossfade", "ken_burns": "zoom_in"},
            ],
            "cta": "CTA",
        }

        with patch("videogen.scriptwriter.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=_mock_gemini_response(llm_output)
            )
            mock_genai.Client.return_value = mock_client

            with patch.dict("os.environ", {"GOOGLE_API_KEY": "fake-key"}):
                script = await generate_script(browse_result, config)

        # index 99 should clamp to index 2 (last screenshot)
        assert script.scenes[0].screenshot_path == browse_result.screenshots[2]

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self, browse_result, config):
        """LLM output wrapped in ```json fences should be handled."""
        raw_json = json.dumps({
            "product_name": "Test",
            "hook": "Hook",
            "scenes": [],
            "cta": "CTA",
        })
        fenced = f"```json\n{raw_json}\n```"

        response = MagicMock()
        response.text = fenced

        with patch("videogen.scriptwriter.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=response)
            mock_genai.Client.return_value = mock_client

            with patch.dict("os.environ", {"GOOGLE_API_KEY": "fake-key"}):
                script = await generate_script(browse_result, config)

        assert script.product_name == "Test"

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, browse_result, config):
        """Should raise ValueError if GOOGLE_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                await generate_script(browse_result, config)
