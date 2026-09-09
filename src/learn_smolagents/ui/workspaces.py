"""Compact workspace picker and destructive confirmation screen."""

import subprocess
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from learn_smolagents.workspace import WorkspaceStore


class DeleteWorkspaceScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "取消")]
    DEFAULT_CSS = """
    DeleteWorkspaceScreen { align: center middle; background: #201e1b 85%; }
    #delete-dialog { width: 62; max-width: 92%; height: auto; padding: 2;
        border: round #e4a293; background: #292520; color: #e8dfd1; }
    #delete-dialog Static { height: auto; margin-bottom: 1; }
    #delete-title { color: #e4a293; text-style: bold; }
    #delete-dialog Input { background: #201e1b; border: tall #665449; margin-bottom: 1; }
    #delete-dialog Input:focus { border: tall #e4a293; }
    #delete-dialog Button { width: 1fr; border: none; background: #393029; color: #e8dfd1; }
    #confirm-delete { background: #8c5148; color: #fff3ed; }
    #delete-error { color: #e4a293; }
    DeleteWorkspaceScreen.small #delete-dialog { padding: 1; }
    DeleteWorkspaceScreen.small #delete-dialog Input { height: 1; border: none; }
    DeleteWorkspaceScreen.small #delete-dialog Horizontal { height: 2; }
    """

    def __init__(self, store: WorkspaceStore, path) -> None:
        super().__init__()
        self.store = store
        self.path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="delete-dialog"):
            yield Static("删除工作区", id="delete-title")
            yield Static(
                f"永久删除 {self.path.name}\n{self.path}\n"
                "目录内全部文件都会被删除。请输入名称确认：",
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
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "关闭")]
    DEFAULT_CSS = """
    WorkspaceManager { align: center middle; background: #201e1b 85%; }
    #workspace-dialog { width: 64; max-width: 92%; height: auto; padding: 2;
        border: round #d99778; background: #292520; color: #e8dfd1; }
    #workspace-dialog Static { height: auto; }
    #manager-title { color: #d99778; text-style: bold; margin-bottom: 1; }
    #current-caption { color: #aaa093; margin-bottom: 1; }
    #workspace-dialog Select { margin-bottom: 1; background: #201e1b; }
    #workspace-dialog SelectCurrent { background: #201e1b; border: tall #665449; }
    #workspace-dialog SelectOverlay { background: #292520; color: #e8dfd1; }
    #workspace-path { background: #201e1b; border: tall #665449; margin-bottom: 1; }
    #workspace-path:focus { border: tall #d99778; }
    .workspace-actions { height: 3; }
    #workspace-dialog Button { border: none; background: #393029; color: #e8dfd1; }
    #open-workspace { background: #d99778; color: #201e1b; text-style: bold; }
    #workspace-dialog Button:hover { background: #665449; }
    #open-workspace:hover { background: #e8dfd1; }
    #delete-workspace { color: #e4a293; background: transparent; text-align: left; }
    #manager-error { color: #e4a293; margin-top: 1; }
    WorkspaceManager.small #workspace-dialog { padding: 1; }
    WorkspaceManager.small .workspace-actions { height: 2; }
    WorkspaceManager.small #workspace-dialog Select { height: 1; border: none; }
    WorkspaceManager.small #workspace-path { height: 1; border: none; }
    """

    def __init__(self, store: WorkspaceStore) -> None:
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(id="workspace-dialog"):
            yield Static("工作区", id="manager-title")
            current = self.store.current.name if self.store.current else "未选择"
            yield Static(f"当前工作区  ·  {current}", id="current-caption")
            yield Select(
                [(f"{path.name}  ·  {path}", str(path)) for path in self.store.paths],
                value=str(self.store.current) if self.store.current else Select.NULL,
                prompt="最近使用的工作区",
                id="workspace-select",
            )
            yield Input(placeholder="输入其他目录路径", id="workspace-path")
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
