"""Tests for modern TUI enhancements: multi-line composer, slash commands, and cancel action."""

import asyncio
import pytest
from textual.widgets import RichLog, Static

from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.composer import PromptInput


class SlowAgent:
    """Agent that runs slowly so cancellation can be tested."""

    def __init__(self, delay: float = 10.0) -> None:
        self.delay = delay
        self.cancelled = False

    def run(self, prompt: str) -> str:
        import time

        time.sleep(self.delay)
        return f"Echo: {prompt}"


class FastAgent:
    def run(self, prompt: str) -> str:
        return f"Fast: {prompt}"


@pytest.mark.asyncio
async def test_composer_multiline_and_history() -> None:
    app = LocalCodeAgentApp(agent=FastAgent())
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        
        # Test newline insertion
        prompt.value = "line 1"
        prompt.action_insert_newline()
        prompt.insert("line 2")
        assert prompt.value == "line 1\nline 2"

        # Submit first prompt
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert "You > line 1\nline 2" in app.transcript

        # Submit second prompt
        prompt.value = "second message"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        # Test history navigation
        prompt.clear()
        prompt.action_history_prev()
        assert prompt.value == "second message"
        prompt.action_history_prev()
        assert prompt.value == "line 1\nline 2"
        prompt.action_history_next()
        assert prompt.value == "second message"


@pytest.mark.asyncio
async def test_slash_command_help_and_clear() -> None:
    app = LocalCodeAgentApp(agent=FastAgent())
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        
        # /help command
        prompt.value = "/help"
        await pilot.press("enter")
        await pilot.pause()
        assert any("快捷指令一览" in entry for entry in app.transcript)

        # /clear command
        prompt.value = "test message"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert len(app.transcript) > 0

        prompt.value = "/clear"
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.transcript) == 0


@pytest.mark.asyncio
async def test_slash_command_mode_toggle() -> None:
    app = LocalCodeAgentApp(agent=FastAgent())
    async with app.run_test() as pilot:
        assert not app.full_access
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "/mode"
        await pilot.press("enter")
        await pilot.pause()
        assert app.full_access


@pytest.mark.asyncio
async def test_ctrl_c_cancels_busy_agent_without_quitting() -> None:
    slow_agent = SlowAgent(delay=5.0)
    app = LocalCodeAgentApp(agent=slow_agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "take a long time"
        await pilot.press("enter")
        await pilot.pause()

        # While busy, press ctrl+c
        assert app.busy
        await pilot.press("ctrl+c")
        await pilot.pause()

        # App should remain open, busy should be cancelled
        assert not app.busy
        assert any("取消" in entry for entry in app.transcript)
        assert not app.is_headless or app.is_running
