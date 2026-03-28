from __future__ import annotations

import json
import logging
import os

from google import genai

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
- End with a clear call-to-action

You output valid JSON matching the required schema."""

USER_PROMPT = """Create a video script for this product:

Product: {product_name}
Tagline: {tagline}
URL: {url}
Key Features:
{features}

Number of screenshots available: {num_screenshots}

Generate a JSON video script with:
- "product_name": the product name
- "hook": attention-grabbing text for the first 3 seconds (bold, short)
- "scenes": array of {num_scenes} scenes, each with:
  - "screenshot_index": which screenshot to use (0-indexed, max {max_index})
  - "headline": short bold text (max 8 words)
  - "subtext": supporting text (max 12 words, or empty string)
  - "duration": seconds (3-5)
  - "transition": one of "crossfade", "fade_black", "slide_left"
  - "ken_burns": one of "zoom_in", "zoom_out", "pan_left", "pan_right"
- "cta": call-to-action text for the final frame

Return ONLY valid JSON, no markdown fences or extra text."""


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
    )

    raw = response.text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

    data = json.loads(raw)

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
