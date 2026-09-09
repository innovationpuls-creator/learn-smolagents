"""Filesystem authorization approval modal screen."""

from __future__ import annotations

from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from learn_smolagents.ui.theme import (
    BG_BASE,
    BG_OVERLAY,
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FG_MUTED,
    FG_PRIMARY,
)


class ApprovalScreen(ModalScreen[bool]):
    """Modal dialog prompting user to authorize filesystem access outside workspace."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "deny", "拒绝"),
        Binding("enter", "allow", "允许"),
    ]
    DEFAULT_CSS = f"""
    ApprovalScreen {{
        align: center middle;
        background: {BG_BASE} 85%;
    }}
    #approval-dialog {{
        width: 68;
        max-width: 95%;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: round {COLOR_WARNING};
        background: {BG_OVERLAY};
        color: {FG_PRIMARY};
    }}
    #approval-title {{
        color: {COLOR_WARNING};
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }}
    #approval-caption {{
        color: {FG_MUTED};
        height: 1;
        margin-bottom: 1;
    }}
    #approval-details {{
        background: {BG_BASE};
        padding: 0 1;
        color: {FG_PRIMARY};
        height: auto;
        margin-bottom: 1;
    }}
    .approval-actions {{
        height: 3;
    }}
    .approval-actions Button {{
        width: 1fr;
        height: 3;
        background: #3c3836;
        color: {FG_PRIMARY};
        border: none;
        margin-right: 1;
    }}
    #deny-access {{
        background: #3c3836;
        color: {COLOR_DANGER};
    }}
    #deny-access:hover {{
        background: #504945;
    }}
    #allow-access {{
        background: {COLOR_SUCCESS};
        color: {BG_BASE};
        text-style: bold;
    }}
    #allow-access:hover {{
        background: #98971a;
    }}
    ApprovalScreen.small #approval-dialog {{
        padding: 1;
    }}
    ApprovalScreen.small .approval-actions {{
        height: 2;
    }}
    ApprovalScreen.small .approval-actions Button {{
        height: 2;
    }}
    """

    def __init__(self, target, operation) -> None:
        super().__init__()
        self.target = target
        self.operation = operation

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-dialog"):
            yield Static("🛡  越界文件访问授权", id="approval-title")
            yield Static("Agent 请求访问当前工作区外的敏感路径：", id="approval-caption")
            yield Static(
                f"操作类型：{self.operation}\n目标路径：{self.target}",
                id="approval-details",
                markup=False,
            )
            with Horizontal(classes="approval-actions"):
                yield Button("拒绝 Esc", id="deny-access")
                yield Button("本次允许", id="allow-access")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.height < 20, "small")

    def on_mount(self) -> None:
        self.query_one("#deny-access", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "allow-access")

    def action_deny(self) -> None:
        self.dismiss(False)

    def action_allow(self) -> None:
        self.dismiss(True)
