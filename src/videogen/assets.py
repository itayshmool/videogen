from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from videogen.config import FONTS_DIR, TMP_DIR
from videogen.models import VideoConfig, VideoScript

logger = logging.getLogger(__name__)


def _load_font(size: int, font_path: Path | None = None, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a font, falling back to system defaults."""
    candidates: list[Path] = []

    if font_path and font_path.exists():
        candidates.append(font_path)

    # Check custom fonts dir
    if FONTS_DIR.exists():
        for f in sorted(FONTS_DIR.glob("*.ttf")):
            candidates.append(f)
        for f in sorted(FONTS_DIR.glob("*.otf")):
            candidates.append(f)

    # Common macOS system fonts
    system_fonts = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/System/Library/Fonts/SFCompact.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf") if bold else Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    candidates.extend(system_fonts)

    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except Exception:
                continue

    return ImageFont.load_default(size=size)


def crop_to_vertical(img: Image.Image, width: int, height: int) -> Image.Image:
    """Center-crop an image to the target vertical aspect ratio, then resize."""
    target_ratio = width / height  # 9:16 = 0.5625
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        # Image is wider — crop sides
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        # Image is taller — crop top/bottom
        new_height = int(img.width / target_ratio)
        top = 0  # Favor keeping the top of the page
        img = img.crop((0, top, img.width, top + new_height))

    return img.resize((width, height), Image.LANCZOS)


def _draw_text_with_background(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    text_color: str = "white",
    bg_color: tuple[int, int, int, int] = (0, 0, 0, 160),
    padding: int = 20,
    max_width: int = 0,
    img_width: int = 1080,
) -> int:
    """Draw text with a semi-transparent background bar. Returns total height used."""
    if not text:
        return 0

    effective_width = max_width or (img_width - padding * 4)

    # Word-wrap the text
    words = text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > effective_width:
            if current_line:
                lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    if not lines:
        return 0

    # Calculate dimensions
    line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    total_text_height = line_height * len(lines) + (len(lines) - 1) * 8
    bar_height = total_text_height + padding * 2
    bar_y = position[1]

    # Draw background bar (full width)
    draw.rectangle(
        [(0, bar_y), (img_width, bar_y + bar_height)],
        fill=bg_color,
    )

    # Draw each line centered
    y = bar_y + padding
    for line in lines:
        bbox = font.getbbox(line)
        text_width = bbox[2] - bbox[0]
        x = (img_width - text_width) // 2
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_height + 8

    return bar_height


def create_scene_frame(
    screenshot_path: Path,
    headline: str,
    subtext: str,
    config: VideoConfig,
    font_path: Path | None = None,
) -> Image.Image:
    """Create a single scene frame: cropped screenshot + text overlay."""
    img = Image.open(screenshot_path).convert("RGBA")
    img = crop_to_vertical(img, config.width, config.height)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Position text in the lower third
    y_start = int(config.height * 0.65)

    if headline:
        font_headline = _load_font(64, font_path, bold=True)
        h = _draw_text_with_background(
            draw, headline.upper(), (0, y_start), font_headline,
            text_color="white", bg_color=(0, 0, 0, 180),
            padding=24, img_width=config.width,
        )
        y_start += h + 8

    if subtext:
        font_sub = _load_font(40, font_path, bold=False)
        _draw_text_with_background(
            draw, subtext, (0, y_start), font_sub,
            text_color="#E0E0E0", bg_color=(0, 0, 0, 140),
            padding=16, img_width=config.width,
        )

    return Image.alpha_composite(img, overlay).convert("RGB")


def create_hook_frame(
    hook_text: str,
    config: VideoConfig,
    font_path: Path | None = None,
) -> Image.Image:
    """Create a hook/title frame with large centered text on dark background."""
    img = Image.new("RGB", (config.width, config.height), (15, 15, 20))
    draw = ImageDraw.Draw(img)

    font = _load_font(80, font_path, bold=True)
    y = config.height // 2 - 80
    _draw_text_with_background(
        draw, hook_text.upper(), (0, y), font,
        text_color="white", bg_color=(0, 0, 0, 0),
        padding=20, img_width=config.width,
    )
    return img


def create_cta_frame(
    cta_text: str,
    product_name: str,
    config: VideoConfig,
    font_path: Path | None = None,
) -> Image.Image:
    """Create a CTA/closing frame."""
    img = Image.new("RGB", (config.width, config.height), (15, 15, 20))
    draw = ImageDraw.Draw(img)

    font_cta = _load_font(72, font_path, bold=True)
    y = config.height // 2 - 100
    _draw_text_with_background(
        draw, cta_text.upper(), (0, y), font_cta,
        text_color="white", bg_color=(0, 0, 0, 0),
        padding=20, img_width=config.width,
    )

    if product_name:
        font_name = _load_font(48, font_path, bold=False)
        _draw_text_with_background(
            draw, product_name, (0, y + 160), font_name,
            text_color="#AAAAAA", bg_color=(0, 0, 0, 0),
            padding=10, img_width=config.width,
        )

    return img


def prepare_assets(script: VideoScript, config: VideoConfig) -> list[Path]:
    """Generate all frame images for the video. Returns ordered list of frame paths."""
    frames_dir = TMP_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    frame_paths: list[Path] = []

    # Hook frame
    hook_img = create_hook_frame(script.hook, config, config.font_path)
    hook_path = frames_dir / "00_hook.png"
    hook_img.save(hook_path)
    frame_paths.append(hook_path)

    # Scene frames
    for i, scene in enumerate(script.scenes):
        frame_img = create_scene_frame(
            scene.screenshot_path, scene.headline, scene.subtext,
            config, config.font_path,
        )
        frame_path = frames_dir / f"{i + 1:02d}_scene.png"
        frame_img.save(frame_path)
        frame_paths.append(frame_path)

    # CTA frame
    cta_img = create_cta_frame(script.cta, script.product_name, config, config.font_path)
    cta_path = frames_dir / f"{len(script.scenes) + 1:02d}_cta.png"
    cta_img.save(cta_path)
    frame_paths.append(cta_path)

    logger.info("Prepared %d frame assets in %s", len(frame_paths), frames_dir)
    return frame_paths
