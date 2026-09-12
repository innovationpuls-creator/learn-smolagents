"""Centralized UI router and modal screen coordinator for Local CodeAgent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from textual.screen import Screen

from learn_smolagents.config import LLMConfig, SettingsStore
from learn_smolagents.ui.screens import (
    ApprovalScreen,
    DeleteWorkspaceScreen,
    SettingsScreen,
    WorkspaceManager,
)
from learn_smolagents.workspace import WorkspaceStore


class RouterHost(Protocol):
    """Structural type of the host app.

    Declared here so this module never imports app.py: app.py imports UIRouter
    at runtime, and the previous TYPE_CHECKING back-reference formed an import
    cycle that basedpyright reported.
    """

    settings_store: SettingsStore
    workspace_store: WorkspaceStore

    @property
    def busy(self) -> bool: ...

    @property
    def screen(self) -> Screen[Any]: ...

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: Any = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> Any: ...

    # Declared as an attribute: App.push_screen is an overloaded method, and
    # Protocol method signatures cannot match a set of overloads.
    push_screen: Callable[..., Any]

    def call_from_thread(
        self, callback: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any: ...

    def _settings_changed(self, config: LLMConfig | None) -> None: ...

    def _workspace_changed(self, changed: bool | None) -> None: ...


class Route(str, Enum):
    """Named routes for screens in Local CodeAgent."""

    SETTINGS = "settings"
    WORKSPACES = "workspaces"
    APPROVAL = "approval"
    DELETE_WORKSPACE = "delete_workspace"


class UIRouter:
    """Coordinates screen navigation, modal dialogs, and thread-to-UI approvals."""

    def __init__(self, app: RouterHost) -> None:
        self.app = app
        self._approval_future: asyncio.Future[bool] | None = None

    def navigate(self, route: Route, **kwargs: Any) -> Any:
        """Declarative route dispatcher."""
        if route == Route.SETTINGS:
            return self.open_settings(kwargs.get("on_dismiss"))
        if route == Route.WORKSPACES:
            return self.open_workspaces(kwargs.get("on_dismiss"))
        if route == Route.APPROVAL:
            return self.request_approval(kwargs["target"], kwargs["operation"])
        if route == Route.DELETE_WORKSPACE:
            return self.open_delete_workspace(kwargs["path"], kwargs.get("on_dismiss"))
        raise ValueError(f"Unknown route: {route}")

    def open_settings(
        self, on_dismiss: Callable[[LLMConfig | None], None] | None = None
    ) -> None:
        """Open the LLM configuration modal screen."""
        if getattr(self.app, "busy", False):
            self.app.notify("请等待当前请求结束后再修改 LLM 配置")
            return
        callback = on_dismiss or getattr(self.app, "_settings_changed", None)
        self.app.push_screen(SettingsScreen(self.app.settings_store), callback)

    def open_workspaces(
        self, on_dismiss: Callable[[bool | None], None] | None = None
    ) -> None:
        """Open the workspace management screen."""
        if isinstance(self.app.screen, WorkspaceManager):
            return
        if getattr(self.app, "busy", False):
            self.app.notify("请等待当前请求结束后再管理工作区")
            return
        callback = on_dismiss or getattr(self.app, "_workspace_changed", None)
        self.app.push_screen(WorkspaceManager(self.app.workspace_store), callback)

    def open_delete_workspace(
        self,
        path: Path,
        on_dismiss: Callable[[bool | None], None] | None = None,
    ) -> None:
        """Open the workspace deletion confirmation modal dialog."""
        self.app.push_screen(DeleteWorkspaceScreen(self.app.workspace_store, path), on_dismiss)

    def request_approval(self, target: Any, operation: str) -> bool:
        """Synchronously request user approval from a background worker thread."""
        return self.app.call_from_thread(self._show_approval, target, operation)

    async def _show_approval(self, target: Any, operation: str) -> bool:
        future = asyncio.get_running_loop().create_future()
        self._approval_future = future

        def answered(value: bool | None) -> None:
            if not future.done():
                future.set_result(bool(value))

        await self.app.push_screen(ApprovalScreen(target, operation), answered)
        try:
            return await future
        finally:
            self._approval_future = None

    def cancel_pending_approval(self) -> None:
        """Cancel any pending approval future upon app exit or screen unmount."""
        if self._approval_future is not None and not self._approval_future.done():
            self._approval_future.set_result(False)
