from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

from videogen.models import (
    BrowseResult,
    KenBurnsDirection,
    Scene,
    TransitionType,
    VideoConfig,
    VideoScript,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a social media video scriptwriter. You create short, punchy scripts
for product showcase videos (15-30 seconds, vertical format for Reels/TikTok/Shorts).

Your style:
- Hook viewers in the first 2 seconds with a bold statement or question
- Keep text SHORT — max 6-8 words per headline, 10-12 words per subtext
- Use power words: "instantly", "effortlessly", "finally", "stop doing X"
- End with a clear call-to-action"""

USER_PROMPT = """Create a video script for this product:

Product: {product_name}
Tagline: {tagline}
URL: {url}
Key Features:
{features}

Number of screenshots available: {num_screenshots}

Generate a video script with {num_scenes} scenes.
Each scene should use a screenshot_index between 0 and {max_index}."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": "string"},
        "hook": {"type": "string", "description": "Attention-grabbing text for the first 3 seconds"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "screenshot_index": {"type": "integer"},
                    "headline": {"type": "string", "description": "Short bold text, max 8 words"},
                    "subtext": {"type": "string", "description": "Supporting text, max 12 words"},
                    "duration": {"type": "number"},
                    "transition": {"type": "string", "enum": ["crossfade", "fade_black", "slide_left"]},
                    "ken_burns": {"type": "string", "enum": ["zoom_in", "zoom_out", "pan_left", "pan_right"]},
                },
                "required": ["screenshot_index", "headline", "subtext", "duration", "transition", "ken_burns"],
            },
        },
        "cta": {"type": "string", "description": "Call-to-action text for the final frame"},
    },
    "required": ["product_name", "hook", "scenes", "cta"],
}


async def generate_script(
    browse_result: BrowseResult,
    config: VideoConfig,
) -> VideoScript:
    """Generate a video script from browsing results using Gemini."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set")

    client = genai.Client(api_key=api_key)

    features_text = "\n".join(f"- {f}" for f in browse_result.features) or "- (none extracted)"
    num_screenshots = len(browse_result.screenshots)
    num_scenes = min(config.max_scenes, num_screenshots)

    user_content = USER_PROMPT.format(
        product_name=browse_result.product_name or "Unknown Product",
        tagline=browse_result.tagline or "",
        url=browse_result.url,
        features=features_text,
        num_screenshots=num_screenshots,
        num_scenes=num_scenes,
        max_index=max(0, num_screenshots - 1),
    )

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\n{user_content}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )

    data = json.loads(response.text)

    # Map scenes from LLM output to our model
    scenes: list[Scene] = []
    for s in data.get("scenes", []):
        idx = s.get("screenshot_index", 0)
        idx = min(idx, num_screenshots - 1)
        scenes.append(
            Scene(
                screenshot_path=browse_result.screenshots[idx],
                headline=s.get("headline", ""),
                subtext=s.get("subtext", ""),
                duration=float(s.get("duration", config.scene_duration)),
                transition=TransitionType(s.get("transition", "crossfade")),
                ken_burns=KenBurnsDirection(s.get("ken_burns", "zoom_in")),
            )
        )

    return VideoScript(
        product_name=data.get("product_name", browse_result.product_name),
        hook=data.get("hook", "Check this out"),
        scenes=scenes,
        cta=data.get("cta", "Learn more"),
    )
