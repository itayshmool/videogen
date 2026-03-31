"""Tests for the browser module — login flow and browsing logic."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from videogen.browser import (
    BROWSE_TASK,
    LOGIN_TASK_PREFIX,
    ProductInfo,
    _make_login_pause_callback,
    browse_product,
)


# ---------------------------------------------------------------------------
# _make_login_pause_callback
# ---------------------------------------------------------------------------


class TestLoginPauseCallback:
    def test_callback_factory_returns_callable(self):
        cb = _make_login_pause_callback("https://example.com")
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_callback_does_not_pause_on_step_0(self):
        cb = _make_login_pause_callback("https://example.com")
        # Step 0 should not trigger the login pause
        await cb(MagicMock(), MagicMock(), 0)

    @pytest.mark.asyncio
    async def test_callback_pauses_on_step_1(self):
        cb = _make_login_pause_callback("https://example.com")
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)
        with patch("asyncio.get_event_loop", return_value=mock_loop), \
             patch("builtins.print"):
            await cb(MagicMock(), MagicMock(), 1)
        mock_loop.run_in_executor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_callback_pauses_only_once(self):
        cb = _make_login_pause_callback("https://example.com")
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)
        with patch("asyncio.get_event_loop", return_value=mock_loop), \
             patch("builtins.print"):
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
    "session": "videogen.browser.BrowserSession",
}


def _mock_session():
    """An AsyncMock BrowserSession so await session.start() etc. work."""
    s = AsyncMock()
    s.get_current_page = AsyncMock(return_value=None)
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
    async def test_login_true_includes_url_and_sets_callback(self, tmp_path):
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

            await browse_product("https://example.com", login=True, headless=False, profile_dir=tmp_path)

        assert "https://example.com" in agent_kwargs["task"]
        assert agent_kwargs["register_new_step_callback"] is not None

    @pytest.mark.asyncio
    async def test_login_false_has_no_callback(self, tmp_path):
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

            await browse_product("https://example.com", login=False, profile_dir=tmp_path)

        assert "https://example.com" in agent_kwargs["task"]
        assert agent_kwargs["register_new_step_callback"] is None


# ---------------------------------------------------------------------------
# browse_product — headless behavior
# ---------------------------------------------------------------------------


class TestBrowseProductHeadless:
    @pytest.mark.asyncio
    async def test_login_forces_headless_false(self, tmp_path):
        all_calls = []

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (all_calls.append(dict(kw)), MagicMock())[1]

            await browse_product("https://example.com", login=True, headless=True, profile_dir=tmp_path)

        # First BrowserProfile call is for the agent (should be headless=False)
        assert all_calls[0]["headless"] is False

    @pytest.mark.asyncio
    async def test_no_login_respects_headless_flag(self, tmp_path):
        profile_kwargs = {}

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (profile_kwargs.update(kw), MagicMock())[1]

            await browse_product("https://example.com", login=False, headless=True, profile_dir=tmp_path)

        assert profile_kwargs["headless"] is True

    @pytest.mark.asyncio
    async def test_passes_user_data_dir(self, tmp_path):
        profile_kwargs = {}

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (profile_kwargs.update(kw), MagicMock())[1]

            await browse_product("https://example.com", login=False, profile_dir=tmp_path)

        assert profile_kwargs["user_data_dir"] == str(tmp_path)


# ---------------------------------------------------------------------------
# browse_product — output parsing
# ---------------------------------------------------------------------------


class TestBrowseProductOutputParsing:
    @pytest.mark.asyncio
    async def test_parses_valid_product_info(self, tmp_path):
        product_json = '{"product_name":"TestProd","tagline":"Best thing","features":["Fast","Easy"],"section_descriptions":["hero shot"]}'

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent(product_json)), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com", profile_dir=tmp_path)

        assert result.product_name == "TestProd"
        assert result.tagline == "Best thing"
        assert result.features == ["Fast", "Easy"]

    @pytest.mark.asyncio
    async def test_handles_none_output(self, tmp_path):
        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent(None)), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com", profile_dir=tmp_path)

        assert result.product_name == ""
        assert result.features == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self, tmp_path):
        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent("not json")), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            result = await browse_product("https://example.com", profile_dir=tmp_path)

        assert result.product_name == ""
        assert result.url == "https://example.com"


# ---------------------------------------------------------------------------
# browse_product — automated login
# ---------------------------------------------------------------------------


AUTO_LOGIN_KWARGS = dict(
    login_url="https://example.com/login",
    username="user@test.com",
    password="secret123",
)


class TestBrowseProductAutoLogin:
    @pytest.mark.asyncio
    async def test_prepends_login_instructions_to_task(self, tmp_path):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockAgent.side_effect = lambda **kw: (agent_kwargs.update(kw), _mock_agent())[1]

            await browse_product("https://example.com", profile_dir=tmp_path, **AUTO_LOGIN_KWARGS)

        assert "https://example.com/login" in agent_kwargs["task"]
        assert "x_username" in agent_kwargs["task"]
        assert "x_password" in agent_kwargs["task"]
        # Also contains the normal browse task
        assert "Analyze the product page at https://example.com" in agent_kwargs["task"]

    @pytest.mark.asyncio
    async def test_passes_sensitive_data_to_agent(self, tmp_path):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockAgent.side_effect = lambda **kw: (agent_kwargs.update(kw), _mock_agent())[1]

            await browse_product("https://example.com", profile_dir=tmp_path, **AUTO_LOGIN_KWARGS)

        assert agent_kwargs["sensitive_data"] == {
            "x_username": "user@test.com",
            "x_password": "secret123",
        }

    @pytest.mark.asyncio
    async def test_does_not_set_step_callback(self, tmp_path):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockAgent.side_effect = lambda **kw: (agent_kwargs.update(kw), _mock_agent())[1]

            await browse_product("https://example.com", profile_dir=tmp_path, **AUTO_LOGIN_KWARGS)

        assert agent_kwargs["register_new_step_callback"] is None

    @pytest.mark.asyncio
    async def test_respects_headless_flag(self, tmp_path):
        profile_kwargs = {}

        with patch(BROWSE_PATCHES["agent"], return_value=_mock_agent()), \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"]) as MockProfile, \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockProfile.side_effect = lambda **kw: (profile_kwargs.update(kw), MagicMock())[1]

            await browse_product(
                "https://example.com", headless=True, profile_dir=tmp_path, **AUTO_LOGIN_KWARGS,
            )

        assert profile_kwargs["headless"] is True

    @pytest.mark.asyncio
    async def test_manual_login_still_works_without_credentials(self, tmp_path):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockAgent.side_effect = lambda **kw: (agent_kwargs.update(kw), _mock_agent())[1]

            await browse_product("https://example.com", login=True, profile_dir=tmp_path)

        assert agent_kwargs["register_new_step_callback"] is not None
        assert agent_kwargs["sensitive_data"] is None

    @pytest.mark.asyncio
    async def test_no_credentials_means_no_sensitive_data(self, tmp_path):
        agent_kwargs = {}

        with patch(BROWSE_PATCHES["agent"]) as MockAgent, \
             patch(BROWSE_PATCHES["llm"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["profile"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["tools"], return_value=MagicMock()), \
             patch(BROWSE_PATCHES["session"], return_value=_mock_session()):
            MockAgent.side_effect = lambda **kw: (agent_kwargs.update(kw), _mock_agent())[1]

            await browse_product("https://example.com", profile_dir=tmp_path)

        assert agent_kwargs["sensitive_data"] is None

    def test_login_task_prefix_has_expected_placeholders(self):
        assert "{login_url}" in LOGIN_TASK_PREFIX
        assert "x_username" in LOGIN_TASK_PREFIX
        assert "x_password" in LOGIN_TASK_PREFIX


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
