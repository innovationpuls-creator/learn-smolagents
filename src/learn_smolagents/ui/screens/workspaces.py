"""Workspace picker and deletion confirmation screens."""

from __future__ import annotations

import subprocess
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from learn_smolagents.ui.theme import (
    BG_BASE,
    BG_BORDER,
    BG_BORDER_FOCUS,
    BG_OVERLAY,
    COLOR_DANGER,
    FG_MUTED,
    FG_PRIMARY,
)
from learn_smolagents.workspace import WorkspaceStore


class DeleteWorkspaceScreen(ModalScreen[bool]):
    """Modal dialog for confirming workspace deletion."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "取消")]
    DEFAULT_CSS = f"""
    DeleteWorkspaceScreen {{
        align: center middle;
        background: {BG_BASE} 85%;
    }}
    #delete-dialog {{
        width: 64;
        max-width: 92%;
        height: auto;
        padding: 1 2;
        border: round {COLOR_DANGER};
        background: {BG_OVERLAY};
        color: {FG_PRIMARY};
    }}
    #delete-dialog Static {{
        height: auto;
        margin-bottom: 0;
    }}
    #delete-title {{
        color: {COLOR_DANGER};
        text-style: bold;
        margin-bottom: 1;
    }}
    #delete-dialog Input {{
        background: {BG_BASE};
        border: round {BG_BORDER};
        color: {FG_PRIMARY};
        margin-top: 1;
        margin-bottom: 1;
    }}
    #delete-dialog Input:focus {{
        border: round {COLOR_DANGER};
    }}
    #delete-dialog Button {{
        width: 1fr;
        border: none;
        background: #3c3836;
        color: {FG_PRIMARY};
    }}
    #confirm-delete {{
        background: {COLOR_DANGER};
        color: {BG_BASE};
        text-style: bold;
    }}
    #confirm-delete:hover {{
        background: #ff6655;
    }}
    #delete-error {{
        color: {COLOR_DANGER};
        height: auto;
    }}
    DeleteWorkspaceScreen.small #delete-dialog {{
        padding: 1;
    }}
    DeleteWorkspaceScreen.small #delete-dialog Input {{
        height: 1;
        border: none;
    }}
    DeleteWorkspaceScreen.small #delete-dialog Horizontal {{
        height: 2;
    }}
    """

    def __init__(self, store: WorkspaceStore, path) -> None:
        super().__init__()
        self.store = store
        self.path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="delete-dialog"):
            yield Static("⚠️ 删除工作区确认", id="delete-title")
            yield Static(
                f"永久删除 {self.path.name}\n{self.path}\n"
                "目录内全部文件都会被物理删除，不可逆。\n请输入文件夹名称确认：",
                markup=False,
            )
            yield Input(placeholder=self.path.name, id="delete-name")
            yield Static("", id="delete-error", markup=False)
            with Horizontal():
                yield Button("取消 Esc", id="cancel-delete")
                yield Button("确认删除", id="confirm-delete")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.height < 20, "small")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "cancel-delete":
            self.dismiss(False)
            return
        if event.button.id != "confirm-delete":
            return
        try:
            self.store.delete(
                self.path, self.query_one("#delete-name", Input).value.strip()
            )
        except (OSError, ValueError) as error:
            self.query_one("#delete-error", Static).update(str(error))
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class WorkspaceManager(ModalScreen[bool]):
    """Modal screen for opening, creating, and switching workspaces."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "关闭")]
    DEFAULT_CSS = f"""
    WorkspaceManager {{
        align: center middle;
        background: {BG_BASE} 85%;
    }}
    #workspace-dialog {{
        width: 66;
        max-width: 92%;
        height: auto;
        padding: 1 2;
        border: round {BG_BORDER_FOCUS};
        background: {BG_OVERLAY};
        color: {FG_PRIMARY};
    }}
    #workspace-dialog Static {{
        height: auto;
    }}
    #manager-title {{
        color: {BG_BORDER_FOCUS};
        text-style: bold;
        margin-bottom: 0;
    }}
    #current-caption {{
        color: {FG_MUTED};
        margin-bottom: 1;
    }}
    #workspace-dialog Select {{
        margin-bottom: 1;
        background: {BG_BASE};
        border: round {BG_BORDER};
    }}
    #workspace-dialog SelectCurrent {{
        background: {BG_BASE};
        color: {FG_PRIMARY};
        border: none;
    }}
    #workspace-dialog SelectOverlay {{
        background: {BG_OVERLAY};
        color: {FG_PRIMARY};
    }}
    #workspace-path {{
        background: {BG_BASE};
        border: round {BG_BORDER};
        color: {FG_PRIMARY};
        margin-bottom: 1;
    }}
    #workspace-path:focus {{
        border: round {BG_BORDER_FOCUS};
    }}
    .workspace-actions {{
        height: 3;
        margin-bottom: 1;
    }}
    #workspace-dialog Button {{
        border: none;
        background: #3c3836;
        color: {FG_PRIMARY};
        height: 3;
    }}
    #open-workspace {{
        background: {BG_BORDER_FOCUS};
        color: {BG_BASE};
        text-style: bold;
        margin-right: 1;
    }}
    #open-workspace:hover {{
        background: #ff9933;
    }}
    #create-workspace:hover {{
        background: #504945;
    }}
    #choose-folder {{
        width: 100%;
        margin-bottom: 1;
    }}
    #delete-workspace {{
        width: 100%;
        color: {COLOR_DANGER};
        background: transparent;
        text-align: left;
    }}
    #delete-workspace:hover {{
        background: #3c3836;
    }}
    #manager-error {{
        color: {COLOR_DANGER};
        margin-top: 1;
    }}
    #close-hint {{
        color: {FG_MUTED};
        text-align: right;
    }}
    WorkspaceManager.small #workspace-dialog {{
        padding: 1;
    }}
    WorkspaceManager.small .workspace-actions {{
        height: 2;
        margin-bottom: 0;
    }}
    WorkspaceManager.small #workspace-dialog Select {{
        height: 1;
        border: none;
        margin-bottom: 0;
    }}
    WorkspaceManager.small #workspace-path {{
        height: 1;
        border: none;
        margin-bottom: 0;
    }}
    WorkspaceManager.small #workspace-dialog Button {{
        height: 2;
    }}
    """

    def __init__(self, store: WorkspaceStore) -> None:
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(id="workspace-dialog"):
            yield Static("📁  工作区管理", id="manager-title")
            current = self.store.current.name if self.store.current else "未选择"
            yield Static(f"当前工作区 · {current}", id="current-caption")
            yield Select(
                [(f"{path.name}  ·  {path}", str(path)) for path in self.store.paths],
                value=str(self.store.current) if self.store.current else Select.NULL,
                prompt="最近使用的工作区",
                id="workspace-select",
            )
            yield Input(placeholder="输入其他目录路径（支持 ~/ 或绝对路径）", id="workspace-path")
            with Horizontal(classes="workspace-actions"):
                yield Button("打开工作区", id="open-workspace")
                yield Button("新建目录", id="create-workspace")
            yield Button("从访达选择目录", id="choose-folder")
            yield Button("删除当前工作区", id="delete-workspace")
            yield Static("", id="manager-error", markup=False)
            yield Static("Esc 关闭", id="close-hint")

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.height < 20, "small")

    def on_select_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self.query_one("#workspace-path", Input).value = event.value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        action = event.button.id
        if action == "close-workspaces":
            self.dismiss(False)
            return
        if action == "delete-workspace":
            if self.store.current is None:
                self.query_one("#manager-error", Static).update("当前没有工作区")
                return
            self.app.push_screen(
                DeleteWorkspaceScreen(self.store, self.store.current),
                self._delete_finished,
            )
            return
        if action == "choose-folder":
            try:
                result = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'POSIX path of (choose folder with prompt "选择工作区目录")',
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                )
            except OSError as error:
                self.query_one("#manager-error", Static).update(
                    f"无法打开目录选择器：{error}"
                )
                return
            if result.returncode == 0 and result.stdout.strip():
                self.query_one("#workspace-path", Input).value = result.stdout.strip()
            elif result.returncode != 1:
                self.query_one("#manager-error", Static).update(
                    result.stderr.strip() or "目录选择失败"
                )
            return
        if action not in ("create-workspace", "open-workspace"):
            return
        try:
            self.store.open(
                self.query_one("#workspace-path", Input).value,
                create=action == "create-workspace",
            )
        except (OSError, ValueError) as error:
            self.query_one("#manager-error", Static).update(str(error))
            return
        self.dismiss(True)

    def _delete_finished(self, deleted: bool | None) -> None:
        if deleted:
            self.dismiss(True)

    def action_close(self) -> None:
        self.dismiss(False)
