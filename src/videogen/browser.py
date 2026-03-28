from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from browser_use import Agent, BrowserProfile, ChatGoogle
from browser_use.browser.session import BrowserSession
from browser_use.tools.service import Tools
from pydantic import BaseModel

from videogen.config import TMP_DIR
from videogen.models import BrowseResult


def _default_llm():
    """Create a Gemini LLM instance from GOOGLE_API_KEY env var."""
    import os

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. "
            "Get one at https://aistudio.google.com/apikey and set it in .env"
        )
    return ChatGoogle(model="gemini-2.5-flash", api_key=api_key)


logger = logging.getLogger(__name__)


class ProductInfo(BaseModel):
    """Structured output the agent returns after browsing."""

    product_name: str
    tagline: str
    features: list[str]
    section_descriptions: list[str]


BROWSE_TASK = """
Analyze the product page you are currently on.

Your goal:
1. Scroll slowly through the ENTIRE page from top to bottom
2. At each major section (hero/header, features, pricing, testimonials, CTA/footer),
   PAUSE and call the `save_screenshot` action with a descriptive label
3. After scrolling through the full page, return structured output with:
   - product_name: the product/company name
   - tagline: the main headline or tagline
   - features: a list of 3-5 key features or selling points
   - section_descriptions: a short description of what each screenshot shows

Take at least 4 screenshots and at most 8. Cover diverse sections of the page.
"""

BROWSE_TASK_NO_LOGIN = """
Visit {url} and analyze the product page.

Your goal:
1. Scroll slowly through the ENTIRE page from top to bottom
2. At each major section (hero/header, features, pricing, testimonials, CTA/footer),
   PAUSE and call the `save_screenshot` action with a descriptive label
3. After scrolling through the full page, return structured output with:
   - product_name: the product/company name
   - tagline: the main headline or tagline
   - features: a list of 3-5 key features or selling points
   - section_descriptions: a short description of what each screenshot shows

Take at least 4 screenshots and at most 8. Cover diverse sections of the page.
"""


def _make_login_step_callback(url: str):
    """Create a step callback that pauses for user login after the agent navigates."""
    login_done = False

    async def on_step(state, output, step_num):
        nonlocal login_done
        if step_num == 1 and not login_done:
            login_done = True
            print("\n" + "=" * 60)
            print("  BROWSER IS OPEN — Please log in now")
            print(f"  URL: {url}")
            print("  When you're done, come back here and press ENTER")
            print("=" * 60 + "\n")
            await asyncio.get_event_loop().run_in_executor(None, input)
            logger.info("User login complete, agent taking over...")

    return on_step


async def browse_product(
    url: str, llm=None, headless: bool = True, login: bool = False,
) -> BrowseResult:
    """Browse a product URL and capture screenshots of key sections.

    Uses Gemini as the default LLM if none is provided.
    If login=True, the agent navigates to the URL, then pauses for user login.
    Returns a BrowseResult with extracted text and screenshot paths.
    """
    if llm is None:
        llm = _default_llm()
    screenshots_dir = TMP_DIR / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    screenshot_paths: list[Path] = []

    tools = Tools()

    @tools.action("Save a screenshot of the current viewport with a label")
    async def save_screenshot(label: str, browser_session):
        idx = len(screenshot_paths)
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        path = screenshots_dir / f"{idx:02d}_{safe_label}.png"
        await browser_session.take_screenshot(path=str(path))
        screenshot_paths.append(path)
        return f"Screenshot saved: {path.name}"

    browser_profile = BrowserProfile(headless=False if login else headless)

    if login:
        # Agent navigates to the URL first, then pauses for user to log in
        task = f"Go to {url} and wait.\n\n" + BROWSE_TASK
        step_callback = _make_login_step_callback(url)
    else:
        task = BROWSE_TASK_NO_LOGIN.format(url=url)
        step_callback = None

    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=browser_profile,
        tools=tools,
        output_model_schema=ProductInfo,
        use_vision=True,
        max_actions_per_step=3,
        register_new_step_callback=step_callback,
    )

    result = await agent.run(max_steps=30)
    await agent.close()

    # Extract structured output
    product_info = result.final_result()
    product_name = ""
    tagline = ""
    features = []

    if product_info:
        try:
            parsed = ProductInfo.model_validate_json(product_info)
            product_name = parsed.product_name
            tagline = parsed.tagline
            features = parsed.features
        except Exception:
            logger.warning("Could not parse structured output, using raw text")
            try:
                data = json.loads(product_info)
                product_name = data.get("product_name", "")
                tagline = data.get("tagline", "")
                features = data.get("features", [])
            except Exception:
                pass

    if not screenshot_paths:
        logger.warning("No screenshots captured by agent, taking fallback screenshot")
        fallback = screenshots_dir / "00_fullpage.png"
        session = BrowserSession(browser_profile=browser_profile)
        await session.start()
        page = await session.get_current_page()
        if page:
            await page.goto(url)
            await asyncio.sleep(2)
            await session.take_screenshot(path=str(fallback), full_page=True)
            screenshot_paths.append(fallback)
        await session.close()

    return BrowseResult(
        product_name=product_name,
        tagline=tagline,
        features=features,
        screenshots=screenshot_paths,
        url=url,
    )
