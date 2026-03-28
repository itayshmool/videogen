"""Tests for the browser module — login flow and browsing logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videogen.browser import (
    BROWSE_TASK,
    BROWSE_TASK_NO_LOGIN,
    ProductInfo,
    _make_login_step_callback,
    browse_product,
)


# ---------------------------------------------------------------------------
# _make_login_step_callback
# ---------------------------------------------------------------------------


class TestLoginStepCallback:
    def test_callback_factory_returns_callable(self):
        cb = _make_login_step_callback("https://example.com")
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_callback_does_not_pause_on_step_0(self):
        cb = _make_login_step_callback("https://example.com")
        await cb(MagicMock(), MagicMock(), 0)

    @pytest.mark.asyncio
    async def test_callback_pauses_on_step_1(self):
        cb = _make_login_step_callback("https://example.com")
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            await cb(MagicMock(), MagicMock(), 1)
        mock_loop.run_in_executor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_callback_pauses_only_once(self):
        cb = _make_login_step_callback("https://example.com")
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            await cb(MagicMock(), MagicMock(), 1)
            await cb(MagicMock(), MagicMock(), 1)
            await cb(MagicMock(), MagicMock(), 2)
        assert mock_loop.run_in_executor.await_count == 1


# ---------------------------------------------------------------------------
# Shared helpers for browse_product tests
# ---------------------------------------------------------------------------

# Patch all external deps so browse_product never touches a real browser.
BROWSE_PATCHES = {
    "agent": "videogen.browser.Agent",
    "llm": "videogen.browser._default_llm",
    "profile": "videogen.browser.BrowserProfile",
    "tools": "videogen.browser.Tools",
    "session": "videogen.browser.BrowserSession",  # prevents fallback browser launch
}


def _mock_session():
    """An AsyncMock BrowserSession so await session.start() etc. work."""
    s = AsyncMock()
    s.get_current_page = AsyncMock(return_value=None)  # no page → skip fallback goto
    return s


def _mock_agent(final_result=None):
    inst = AsyncMock()
    inst.run = AsyncMock(
        return_value=MagicMock(final_result=MagicMock(return_value=final_result))
    )
    inst.close = AsyncMock()
    return inst


# ---------------------------------------------------------------------------
# browse_product — task selection
# ---------------------------------------------------------------------------


class TestBrowseProductTaskSelection:
    @pytest.mark.asyncio
    async def test_login_true_uses_login_task_with_url(self):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):

            def capture(**kwargs):
                agent_kwargs.update(kwargs)
                return _mock_agent()
            MockAgent.side_effect = capture

            await browse_product("https://example.com", login=True, headless=False)

        assert "https://example.com" in agent_kwargs["task"]
        assert "Analyze the product page" in agent_kwargs["task"]
        assert agent_kwargs["register_new_step_callback"] is not None

    @pytest.mark.asyncio
    async def test_login_false_uses_no_login_task(self):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):

            def capture(**kwargs):
                agent_kwargs.update(kwargs)
                return _mock_agent()
            MockAgent.side_effect = capture

            await browse_product("https://example.com", login=False)

        assert "Visit https://example.com" in agent_kwargs["task"]
        assert agent_kwargs["register_new_step_callback"] is None


# ---------------------------------------------------------------------------
# browse_product — headless behavior
# ---------------------------------------------------------------------------


class TestBrowseProductHeadless:
    @pytest.mark.asyncio
    async def test_login_forces_headless_false(self):
        profile_kwargs = {}

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (profile_kwargs.update(kw), MagicMock())[1]

            await browse_product("https://example.com", login=True, headless=True)

        assert profile_kwargs["headless"] is False

    @pytest.mark.asyncio
    async def test_no_login_respects_headless_flag(self):
        profile_kwargs = {}

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (profile_kwargs.update(kw), MagicMock())[1]

            await browse_product("https://example.com", login=False, headless=True)

        assert profile_kwargs["headless"] is True


# ---------------------------------------------------------------------------
# browse_product — output parsing
# ---------------------------------------------------------------------------


class TestBrowseProductOutputParsing:
    @pytest.mark.asyncio
    async def test_parses_valid_product_info(self):
        product_json = '{"product_name":"TestProd","tagline":"Best thing","features":["Fast","Easy"],"section_descriptions":["hero shot"]}'

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent(product_json)), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com")

        assert result.product_name == "TestProd"
        assert result.tagline == "Best thing"
        assert result.features == ["Fast", "Easy"]

    @pytest.mark.asyncio
    async def test_handles_none_output(self):
        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent(None)), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com")

        assert result.product_name == ""
        assert result.features == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent("not json")), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com")

        assert result.product_name == ""
        assert result.url == "https://example.com"


# ---------------------------------------------------------------------------
# ProductInfo model
# ---------------------------------------------------------------------------


class TestProductInfoModel:
    def test_valid(self):
        info = ProductInfo(
            product_name="Foo", tagline="Bar",
            features=["a"], section_descriptions=["hero"],
        )
        assert info.product_name == "Foo"

    def test_requires_all_fields(self):
        with pytest.raises(Exception):
            ProductInfo(product_name="Foo")
