"""Conversation timeline log and stream thought display component."""

from __future__ import annotations

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from learn_smolagents.ui.theme import (
    ACCENT_WARM,
    BG_BASE,
    COLOR_DANGER,
    COLOR_INFO,
    FG_PRIMARY,
)


class ConversationView(Vertical):
    """Container wrapping the message timeline log, live thoughts, and status line."""

    DEFAULT_CSS = f"""
    ConversationView {{
        height: 1fr;
    }}
    #conversation, #conversation:focus {{
        height: 1fr;
        padding: 0 1;
        border: none;
        background: {BG_BASE};
        background-tint: transparent;
        color: {FG_PRIMARY};
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-size-vertical: 0;
    }}
    #live-thought {{
        display: none;
        height: auto;
        max-height: 5;
        color: {COLOR_INFO};
        margin: 0 1;
        padding: 0 1;
        border-left: solid {COLOR_INFO};
    }}
    #status {{
        height: 1;
        color: {ACCENT_WARM};
        margin: 1 1 0 1;
    }}
    #status.error {{
        color: {COLOR_DANGER};
    }}
    """

    def compose(self) -> ComposeResult:
        yield RichLog(id="conversation", wrap=True, markup=False, min_width=1)
        yield Static("", id="live-thought", markup=False)
        yield Static("", id="status", markup=False)

    @property
    def log(self) -> RichLog:
        return self.query_one("#conversation", RichLog)

    def write_entry(self, heading: RenderableType, body: RenderableType) -> None:
        log = self.log
        log.write(heading)
        log.write(body)
        log.write("")
        self.call_after_refresh(log.scroll_end, animate=False, x_axis=False)

    def clear(self) -> None:
        self.log.clear()

    def set_live_thought(self, text: str) -> None:
        live = self.query_one("#live-thought", Static)
        if text:
            live.update(f"◇ 思考中...\n{text}")
            live.display = True
        else:
            live.display = False

    def hide_live_thought(self) -> None:
        self.query_one("#live-thought", Static).display = False

    def set_status(self, message: str, *, error: bool = False) -> None:
        status = self.query_one("#status", Static)
        status.update(message)
        status.set_class(error, "error")
        status.display = bool(message)
