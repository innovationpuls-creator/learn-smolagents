"""Composer component with multi-line prompt input and command help."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, TextArea

from learn_smolagents.ui.theme import (
    ACCENT_ROSE,
    ACCENT_WARM,
    BG_BORDER,
    BG_BORDER_FOCUS,
    BG_SURFACE,
    FG_MUTED,
    FG_PRIMARY,
)


@runtime_checkable
class _CancelHost(Protocol):
    """Host app exposing the cancel/quit action, without importing app.py."""

    def action_cancel_or_quit(self) -> None: ...


class PromptInput(TextArea):
    """Multi-line prompt input area with history navigation and keyboard shortcuts."""

    DEFAULT_CSS = f"""
    PromptInput {{
        height: 1fr;
        width: 1fr;
        padding: 0;
        border: none;
        background: transparent;
        color: {FG_PRIMARY};
    }}
    PromptInput:focus {{
        border: none;
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "submit", "发送", priority=True),
        Binding("shift+enter", "insert_newline", "换行", priority=True),
        Binding("alt+enter", "insert_newline", "换行", priority=True),
        Binding("ctrl+j", "insert_newline", "换行", priority=True),
        Binding("up", "history_prev", "上一条", priority=False),
        Binding("down", "history_next", "下一条", priority=False),
    ]

    class Submitted(Message):
        """Posted when user presses Enter to submit a prompt."""

        def __init__(self, input_widget: PromptInput, value: str) -> None:
            super().__init__()
            self.input = input_widget
            self.value = value

    def __init__(
        self,
        text: str = "",
        *,
        placeholder: str = "想聊些什么？（Enter 发送 · Shift+Enter 换行 · / 指令）",
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(
            text=text,
            placeholder=placeholder,
            id=id,
            classes=classes,
            show_line_numbers=False,
            soft_wrap=True,
        )
        self._history: list[str] = []
        self._history_idx: int = -1
        self._temp_draft: str = ""

    @property
    def value(self) -> str:
        return self.text

    @value.setter
    def value(self, val: str) -> None:
        self.load_text(val)
        self._move_cursor_to_end()

    def _move_cursor_to_end(self) -> None:
        last_line = max(0, self.document.line_count - 1)
        last_col = len(self.document.get_line(last_line))
        self.move_cursor((last_line, last_col))

    def action_submit(self) -> None:
        """Submit the current prompt text."""
        content = self.text.strip()
        if not content:
            return
        if getattr(self.app, "busy", False):
            return
        if not self._history or self._history[-1] != content:
            self._history.append(content)
        self._history_idx = len(self._history)
        self._temp_draft = ""
        self.post_message(self.Submitted(self, content))

    def action_insert_newline(self) -> None:
        """Insert a line break at current cursor."""
        self.insert("\n")

    def action_history_prev(self) -> None:
        """Navigate backwards in prompt history."""
        if not self.cursor_at_first_line and self.text:
            self.action_cursor_up()
            return
        if not self._history:
            return
        if self._history_idx == len(self._history):
            self._temp_draft = self.text
        if self._history_idx > 0:
            self._history_idx -= 1
            self.load_text(self._history[self._history_idx])
            self._move_cursor_to_end()

    def action_copy(self) -> None:
        """Copy selected text, or delegate to app cancel/quit when no selection."""
        if self.selected_text:
            super().action_copy()
        elif isinstance(self.app, _CancelHost):
            self.app.action_cancel_or_quit()
        else:
            super().action_copy()

    def action_history_next(self) -> None:
        """Navigate forwards in prompt history."""
        if not self.cursor_at_last_line and self.text:
            self.action_cursor_down()
            return
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.load_text(self._history[self._history_idx])
            self._move_cursor_to_end()
        elif self._history_idx == len(self._history) - 1:
            self._history_idx = len(self._history)
            self.load_text(self._temp_draft)
            self._move_cursor_to_end()


class ComposerView(Vertical):
    """Container wrapping the prompt input row and footer help text."""

    DEFAULT_CSS = f"""
    ComposerView {{
        height: auto;
    }}
    #composer {{
        height: 5;
        margin-top: 1;
        padding: 1 2;
        border: round {BG_BORDER};
        background: {BG_SURFACE};
    }}
    #composer:focus-within {{
        border: round {BG_BORDER_FOCUS};
    }}
    #composer.running {{
        border: round {ACCENT_ROSE};
    }}
    #input-row {{
        height: 1fr;
    }}
    #prompt-mark {{
        width: 3;
        color: {ACCENT_WARM};
        text-style: bold;
    }}
    #help {{
        height: 1;
        color: {FG_MUTED};
        margin: 0 1;
    }}
    Screen.compact #composer {{
        height: 3;
        padding: 0 1;
    }}
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="composer"), Horizontal(id="input-row"):
            yield Static("❯", id="prompt-mark", markup=False)
            yield PromptInput(id="prompt")
        yield Static(
            "Enter 发送 · Shift+Enter 换行 · Ctrl+W 工作区 · /help 指令 · Ctrl+C 中断/退出",
            id="help",
            markup=False,
        )

    def set_running(self, running: bool) -> None:
        composer = self.query_one("#composer")
        composer.set_class(running, "running")
        help_text = self.query_one("#help", Static)
        if running:
            help_text.update("处理中 · Ctrl+C 中断当前任务")
        else:
            help_text.update(
                "Enter 发送 · Shift+Enter 换行 · Ctrl+W 工作区 · /help 指令 · Ctrl+C 中断/退出"
            )
