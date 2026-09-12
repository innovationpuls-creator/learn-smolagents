"""Header component displaying brand identity, environment pills, and workspace controls."""

from __future__ import annotations

import os

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from learn_smolagents.ui.theme import (
    ACCENT_ROSE,
    ACCENT_WARM,
    BG_BORDER,
    BG_HOVER,
    BG_OVERLAY,
    BG_SURFACE,
    COLOR_INFO,
    COLOR_SUCCESS,
    FG_PRIMARY,
)


class HeaderBar(Vertical):
    """Refined two-row header component with status badges and navigation buttons."""

    DEFAULT_CSS = f"""
    HeaderBar {{
        height: 4;
        border-bottom: solid {BG_BORDER};
        margin-bottom: 1;
    }}
    #header {{
        height: 4;
    }}
    #identity {{
        height: 1;
    }}
    #brand {{
        width: 1fr;
        color: {FG_PRIMARY};
        text-style: bold;
    }}
    #header-pills {{
        width: auto;
        height: 1;
    }}
    #env-badge {{
        background: {BG_OVERLAY};
        color: {ACCENT_ROSE};
        padding: 0 1;
        margin-right: 1;
        text-style: bold;
    }}
    #agent-pill {{
        background: {BG_OVERLAY};
        color: {COLOR_SUCCESS};
        padding: 0 1;
    }}
    #edition {{
        display: none;
    }}
    #workspace-row {{
        height: 1;
        margin-top: 1;
    }}
    #workspace {{
        height: 1;
        width: 1fr;
        color: {FG_PRIMARY};
        background: {BG_SURFACE};
        border: none;
        padding: 0 1;
        content-align: left middle;
    }}
    #workspace:hover {{
        background: {BG_HOVER};
        color: {ACCENT_WARM};
    }}
    #workspace:focus {{
        text-style: bold;
        color: {FG_PRIMARY};
        background: {BG_HOVER};
    }}
    #llm-settings {{
        height: 1;
        width: auto;
        min-width: 12;
        padding: 0 1;
        border: none;
        background: {BG_SURFACE};
        color: {ACCENT_WARM};
        margin-left: 1;
    }}
    #llm-settings:hover {{
        background: {BG_HOVER};
    }}
    #permission-mode {{
        height: 1;
        width: auto;
        min-width: 10;
        padding: 0 1;
        border: none;
        background: {BG_SURFACE};
        color: {COLOR_INFO};
        margin-left: 1;
    }}
    #permission-mode:hover {{
        background: {BG_HOVER};
    }}
    Screen.compact HeaderBar {{
        height: 3;
        margin-bottom: 0;
    }}
    Screen.compact #workspace-row {{
        margin-top: 0;
    }}
    """

    def __init__(
        self,
        workspace_label: str = "📁  尚未选择工作区",
        workspace_tooltip: str = "尚未选择工作区",
        llm_label: str = "⚙  未配模型",
        full_access: bool = False,
        id: str = "header",
    ) -> None:
        super().__init__(id=id)
        self._initial_workspace_label = workspace_label
        self._initial_workspace_tooltip = workspace_tooltip
        self._initial_llm_label = llm_label
        self._initial_full_access = full_access

    def compose(self) -> ComposeResult:
        env_name = os.environ.get("LEARN_SMOLAGENTS_ENV", "dev").upper()
        with Horizontal(id="identity"):
            yield Static(
                Text.assemble(("✳  ", ACCENT_WARM), "Local CodeAgent"), id="brand"
            )
            with Horizontal(id="header-pills"):
                yield Static(f" {env_name} ", id="env-badge")
                yield Static("● 就绪", id="agent-pill")
            yield Static("S M O L A G E N T S", id="edition", markup=False)
        with Horizontal(id="workspace-row"):
            directory = Button(
                self._initial_workspace_label, id="workspace", compact=True
            )
            directory.tooltip = self._initial_workspace_tooltip
            yield directory
            yield Button(self._initial_llm_label, id="llm-settings", compact=True)
            permission = Button(
                "完全访问" if self._initial_full_access else "区外审批",
                id="permission-mode",
                compact=True,
            )
            permission.tooltip = (
                "工作区内允许读写和删除，工作区外需审批；完全访问模式不询问。"
            )
            yield permission

    def update_workspace(self, label: str, tooltip: str) -> None:
        directory = self.query_one("#workspace", Button)
        directory.label = label
        directory.tooltip = tooltip

    def update_llm(self, label: str) -> None:
        self.query_one("#llm-settings", Button).label = label

    def update_permission(self, full_access: bool) -> None:
        compact = self.screen.has_class("compact")
        self.query_one("#permission-mode", Button).label = (
            "完全访问"
            if full_access
            else "区外审批"
            if compact
            else "区内允许 · 区外审批"
        )

    def update_agent_status(self, status: str) -> None:
        self.query_one("#agent-pill", Static).update(status)
