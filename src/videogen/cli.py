from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import typer

from videogen.config import OUTPUT_DIR, PROFILE_DIR, TMP_DIR

app = typer.Typer(
    name="videogen",
    help="Generate social video clips from product pages.",
    no_args_is_help=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("videogen")


async def _run_pipeline(
    url: str,
    max_scenes: int,
    scene_duration: float,
    music: Path | None,
    output_dir: Path,
    headless: bool,
    login: bool,
    keep_tmp: bool,
    profile_dir: Path = PROFILE_DIR,
    login_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    custom_task: str | None = None,
    landscape: bool = False,
) -> Path:
    from videogen.assets import prepare_assets
    from videogen.browser import browse_product
    from videogen.composer import compose_video
    from videogen.models import VideoConfig
    from videogen.scriptwriter import generate_script

    config = VideoConfig(
        width=1920 if landscape else 1080,
        height=1080 if landscape else 1920,
        max_scenes=max_scenes,
        scene_duration=scene_duration,
        music_path=music,
        output_dir=output_dir,
        crop=not landscape,
    )

    # Step 1: Browse
    logger.info("Browsing %s ...", url)
    browse_result = await browse_product(
        url,
        headless=headless,
        login=login,
        profile_dir=profile_dir,
        login_url=login_url,
        username=username,
        password=password,
        custom_task=custom_task,
    )
    logger.info(
        "Captured %d screenshots for '%s'",
        len(browse_result.screenshots),
        browse_result.product_name or url,
    )

    # Step 2: Generate script
    logger.info("Generating video script ...")
    script = await generate_script(browse_result, config)
    logger.info("Script: hook='%s', %d scenes, cta='%s'", script.hook, len(script.scenes), script.cta)

    # Step 3: Prepare frame assets
    logger.info("Preparing frame assets ...")
    frame_paths = prepare_assets(script, config)
    logger.info("Generated %d frame images", len(frame_paths))

    # Step 4: Compose video
    logger.info("Composing final video ...")
    output_path = compose_video(script, frame_paths, config)
    logger.info("Done! Video saved to: %s", output_path)

    # Cleanup
    if not keep_tmp and TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
        logger.info("Cleaned up temp files")

    return output_path


@app.command()
def generate(
    url: str = typer.Argument(help="Product page URL to generate a video for"),
    scenes: int = typer.Option(5, "--scenes", "-s", help="Max number of scenes"),
    duration: float = typer.Option(4.0, "--duration", "-d", help="Duration per scene in seconds"),
    music: Path | None = typer.Option(None, "--music", "-m", help="Background music file path"),
    output_dir: Path = typer.Option(OUTPUT_DIR, "--output", "-o", help="Output directory"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser headlessly"),
    login: bool = typer.Option(False, "--login", "-l", help="Pause for manual login before capturing"),
    profile_dir: Path = typer.Option(PROFILE_DIR, "--profile", "-p", help="Browser profile directory (persists login sessions)"),
    keep_tmp: bool = typer.Option(False, "--keep-tmp", help="Keep temp files after generation"),
    login_url: str | None = typer.Option(None, "--login-url", help="Login page URL (enables automated login)"),
    username: str | None = typer.Option(None, "--username", "-u", help="Username/email for automated login"),
    password: str | None = typer.Option(None, "--password", help="Password for automated login"),
    task: str | None = typer.Option(None, "--task", "-t", help="Custom browsing instructions for the agent"),
    landscape: bool = typer.Option(False, "--landscape", help="Landscape mode (1920x1080) — full screenshots without cropping"),
) -> None:
    """Generate a social video clip from a product page URL."""
    creds = [login_url, username, password]
    if any(creds) and not all(creds):
        typer.echo("Error: --login-url, --username, and --password must all be provided together.", err=True)
        raise typer.Exit(1)

    output_path = asyncio.run(
        _run_pipeline(
            url, scenes, duration, music, output_dir, headless, login, keep_tmp, profile_dir,
            login_url=login_url, username=username, password=password, custom_task=task,
            landscape=landscape,
        )
    )
    typer.echo(f"\nVideo: {output_path}")


if __name__ == "__main__":
    app()
