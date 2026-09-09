from __future__ import annotations

from typing import Protocol

import pytest
from textual.widgets import Input

from learn_smolagents.ui.app import LocalCodeAgentApp


class AgentRunner(Protocol):
    def run(self, prompt: str) -> str: ...


class StubAgent:
    def run(self, prompt: str) -> str:
        return f"Agent answer: {prompt}"


class FailingAgent:
    def run(self, prompt: str) -> str:
        raise RuntimeError("LM Studio is unavailable")


@pytest.mark.asyncio
async def test_submitting_a_prompt_displays_user_message_and_agent_response() -> None:
    app = LocalCodeAgentApp(agent=StubAgent())

    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        prompt.value = "Where is the model configured?"
        await pilot.click("#prompt")
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert "You > Where is the model configured?" in app.transcript
        assert "Agent > Agent answer: Where is the model configured?" in app.transcript


@pytest.mark.asyncio
async def test_agent_error_is_shown_without_closing_the_tui() -> None:
    app = LocalCodeAgentApp(agent=FailingAgent())

    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", Input)
        prompt.value = "Read the workspace"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert "Error > LM Studio is unavailable" in app.transcript


@pytest.mark.asyncio
async def test_pending_request_preserves_draft_and_prevents_overlapping_calls() -> None:
    import threading

    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    class WaitingAgent:
        def run(self, prompt: str) -> str:
            calls.append(prompt)
            started.set()
            release.wait(timeout=5)
            return "完成"

    app = LocalCodeAgentApp(agent=WaitingAgent())
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", Input)
        prompt.value = "first"
        await pilot.press("enter")
        try:
            await pilot.pause()
            assert started.is_set()
            from textual.widgets import Static

            status = app.query_one("#status", Static)
            assert status.display
            assert "正在处理" in str(status.content)
            assert app.query_one("#composer").has_class("running")
            prompt.value = "second"
            await pilot.press("enter")
            assert calls == ["first"]
            assert prompt.value == "second"
        finally:
            release.set()
        await app.workers.wait_for_complete()
        assert not app.query_one("#status").display
        assert not app.query_one("#composer").has_class("running")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert calls == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(100, 30), (48, 18)])
async def test_startup_is_quiet_and_input_fits(size: tuple[int, int]) -> None:
    from textual.widgets import Static

    app = LocalCodeAgentApp(agent=StubAgent())
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert app.transcript == []
        assert not app.query_one("#status", Static).display
        prompt = app.query_one("#prompt", Input)
        assert prompt.has_focus
        assert prompt.region.right <= size[0]
        assert prompt.region.bottom < size[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(132, 39), (48, 18)])
async def test_conversation_has_uniform_warm_background_with_either_focus(size) -> None:
    from rich.color import Color
    from textual.widgets import RichLog

    app = LocalCodeAgentApp(agent=StubAgent())
    async with app.run_test(size=size) as pilot:
        log = app.query_one("#conversation", RichLog)
        app._append("You", "你好")
        await pilot.pause()
        for target in ("#prompt", "#conversation"):
            app.query_one(target).focus()
            await pilot.pause()
            assert not log.show_vertical_scrollbar
            region = log.region
            backgrounds = {
                app.screen._compositor.get_style_at(x, y).bgcolor
                for y in range(region.y, region.bottom)
                for x in range(region.x, region.right)
            }
            assert backgrounds == {Color.parse("#201e1b")}


@pytest.mark.asyncio
async def test_long_conversation_scrolls_without_covering_input() -> None:
    from textual.widgets import RichLog

    app = LocalCodeAgentApp(agent=StubAgent())
    async with app.run_test(size=(48, 18)) as pilot:
        app._append("Agent", "\n\n".join(f"第 {n} 段回答" for n in range(30)))
        await pilot.pause()
        log = app.query_one("#conversation", RichLog)
        assert log.show_vertical_scrollbar
        assert log.scroll_y == log.max_scroll_y
        assert log.region.bottom < app.query_one("#prompt", Input).region.y
        log.focus()
        await pilot.press("home")
        await pilot.pause()
        assert log.scroll_y == 0


@pytest.mark.asyncio
async def test_welcome_collapses_and_layout_adapts_during_resize() -> None:
    app = LocalCodeAgentApp(agent=StubAgent())
    async with app.run_test(size=(132, 39)) as pilot:
        welcome = app.query_one("#welcome")
        assert welcome.display
        assert app.query_one("#sigil").region.x >= welcome.region.x
        await pilot.resize_terminal(48, 18)
        await pilot.pause()
        assert app.screen.has_class("compact")
        prompt = app.query_one("#prompt", Input)
        prompt.value = "你好"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert not welcome.display
        await pilot.resize_terminal(132, 39)
        await pilot.pause()
        assert not app.screen.has_class("compact")
        assert prompt.region.right <= 132


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(132, 39), (48, 18)])
async def test_welcome_graphic_and_composer_form_a_single_group(size) -> None:
    from textual.widgets import Static

    app = LocalCodeAgentApp(agent=StubAgent())
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        mark = app.query_one("#sigil", Static)
        copy = app.query_one("#welcome-copy")
        welcome = app.query_one("#welcome")
        composer = app.query_one("#composer")
        assert mark.region.right <= copy.region.x
        assert copy.region.right <= welcome.region.right
        assert 0 <= composer.region.y - welcome.region.bottom <= 1
        assert any(0x2800 <= ord(char) <= 0x28ff for char in str(mark.content))
