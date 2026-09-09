"""Warm, refined, modular terminal interface for Local CodeAgent."""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import ClassVar, Protocol

from rich.markdown import Markdown
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.geometry import Size
from textual.widgets import Button, Input, RichLog, Static

from learn_smolagents.agent import SmolAgentRunner
from learn_smolagents.config import SettingsStore
from learn_smolagents.ui.components import (
    ComposerView,
    ConversationView,
    HeaderBar,
    PromptInput,
    WelcomeView,
    render_mark,
)
from learn_smolagents.ui.router import Route, UIRouter
from learn_smolagents.ui.theme import (
    ACCENT_WARM,
    BACKGROUND,
    BG_BASE,
    CODE_THEME,
    COLOR_DANGER,
    FG_MUTED,
    FG_PRIMARY,
    FOREGROUND,
    MARKDOWN_THEME,
    MUTED,
    format_agent_turn_header,
    format_error_header,
    format_thought_header,
    format_timeline_body,
    format_tool_header,
    format_user_turn_header,
)
from learn_smolagents.workspace import Workspace, WorkspaceStore


class AgentRunner(Protocol):
    """The small interface the TUI needs from an Agent."""

    def run(self, prompt: str) -> str: ...


class LocalCodeAgentApp(App[None]):
    """A focused, modular TUI for local workspace management and Agent sessions."""

    TITLE = "Local CodeAgent"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "cancel_or_quit", "中断/退出", show=False, priority=True),
        Binding("ctrl+w", "workspaces", "工作区", show=False, priority=True),
    ]
    CSS = f"""
    Screen {{
        background: {BG_BASE};
        color: {FG_PRIMARY};
        align-horizontal: center;
    }}
    #shell {{
        width: 100%;
        max-width: 116;
        padding: 1 4;
    }}
    #body {{
        height: 1fr;
    }}
    #shell.empty {{
        align-vertical: middle;
    }}
    #shell.empty HeaderBar {{
        dock: top;
    }}
    #shell.empty #body {{
        height: auto;
    }}
    #shell.empty WelcomeView {{
        height: 14;
    }}
    #shell.empty ComposerView #composer {{
        margin-top: 1;
    }}
    #shell.empty ComposerView #help {{
        margin-bottom: 2;
    }}
    Screen.compact #shell {{
        padding: 0 2;
    }}
    Screen.compact #shell.empty WelcomeView {{
        height: 6;
    }}
    Screen.compact #shell.empty ComposerView #help {{
        margin-bottom: 0;
    }}
    """

    def __init__(
        self,
        agent: AgentRunner | None = None,
        *,
        workspace_store: WorkspaceStore | None = None,
        settings_store: SettingsStore | None = None,
    ) -> None:
        super().__init__()
        self.settings_store = settings_store or SettingsStore()
        self.llm_config = self.settings_store.load()
        self.workspace_store = workspace_store or WorkspaceStore()
        self.workspace = Workspace(self.workspace_store.current)
        self.full_access = False
        self._external_agent = agent

        # Router for screen and modal workflow orchestration
        self.router = UIRouter(self)

        self.agent = (
            agent
            if agent is not None
            else SmolAgentRunner(
                self.workspace,
                approval=self._request_approval,
                full_access=self.full_access,
                config=self.llm_config,
            )
        )
        self.transcript: list[str] = []
        self.busy = False
        self._started_at = 0.0
        self._frame = 0
        self._turn = 0
        self._stream_thought = ""

    @property
    def _approval_future(self):
        """Backward-compatibility access to approval future."""
        return self.router._approval_future

    @_approval_future.setter
    def _approval_future(self, value):
        self.router._approval_future = value

    def compose(self) -> ComposeResult:
        with Vertical(id="shell", classes="empty"):
            yield HeaderBar(
                workspace_label=self._workspace_label(),
                workspace_tooltip=(
                    str(self.workspace.root)
                    if self.workspace.root
                    else "尚未选择工作区"
                ),
                llm_label=self._llm_label(),
                full_access=self.full_access,
            )
            with Vertical(id="body"):
                yield WelcomeView()
                yield ConversationView()
            yield ComposerView()

    def _workspace_label(self) -> str:
        root = self.workspace.root
        return f"📁  {root.name}" if root else "📁  尚未选择工作区"

    def _llm_label(self) -> str:
        return f"⚙  {self.llm_config.model_id or '未配模型'}"

    def _request_approval(self, target, operation):
        return self.router.request_approval(target, operation)

    def on_unmount(self) -> None:
        self.router.cancel_pending_approval()

    def action_cancel_or_quit(self) -> None:
        """Cancel current running agent turn if busy, or exit the app if idle."""
        if self.busy:
            for worker in self.workers:
                if not worker.is_finished:
                    worker.cancel()
            self.busy = False
            self.query_one(ComposerView).set_running(False)
            self._set_status("! 当前请求已取消", error=True)
            self._append("Error", "任务已被用户取消 (Ctrl+C)")
            self.query_one(HeaderBar).update_agent_status("● 就绪")
            self.notify("当前任务已取消", severity="warning")
        else:
            self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "llm-settings":
            self.router.open_settings(self._settings_changed)
            return
        if event.button.id == "permission-mode":
            if self.busy:
                self.notify("请等待当前请求结束后再切换权限")
                return
            self.full_access = not self.full_access
            if self._external_agent is None:
                self.agent = SmolAgentRunner(
                    self.workspace,
                    approval=self._request_approval,
                    full_access=self.full_access,
                    config=self.llm_config,
                )
            self.query_one(HeaderBar).update_permission(self.full_access)
            return
        if event.button.id in {"workspace", "manage-workspaces"}:
            self.action_workspaces()

    def _settings_changed(self, config) -> None:
        if config is None:
            return
        self.llm_config = config
        if self._external_agent is None:
            self.agent = SmolAgentRunner(
                self.workspace,
                approval=self._request_approval,
                full_access=self.full_access,
                config=config,
            )
        self.transcript.clear()
        self._turn = 0
        conv = self.query_one(ConversationView)
        conv.clear()
        conv.display = False
        self.query_one(WelcomeView).display = True
        self.query_one("#shell").add_class("empty")

        header = self.query_one(HeaderBar)
        header.update_workspace(
            self._workspace_label(),
            str(self.workspace.root) if self.workspace.root else "尚未选择工作区",
        )
        header.update_llm(self._llm_label())
        self._set_status("")
        self.query_one("#prompt", PromptInput).focus()

    def action_workspaces(self) -> None:
        self.router.open_workspaces(self._workspace_changed)

    def _workspace_changed(self, changed: bool | None) -> None:
        self._adapt_layout()
        if changed and self.workspace.root != self.workspace_store.current:
            if self.workspace_store.current is None:
                self.workspace.root = None
            else:
                self.workspace.switch(self.workspace_store.current)
            if self._external_agent is None:
                self.agent = SmolAgentRunner(
                    self.workspace,
                    approval=self._request_approval,
                    full_access=self.full_access,
                    config=self.llm_config,
                )
            self.transcript.clear()
            self._turn = 0
            conv = self.query_one(ConversationView)
            conv.clear()
            conv.display = False
            self.query_one(WelcomeView).display = True
            self.query_one("#shell").add_class("empty")
            self._set_status("")

        header = self.query_one(HeaderBar)
        header.update_workspace(
            self._workspace_label(),
            str(self.workspace.root) if self.workspace.root else "尚未选择工作区",
        )
        header.update_llm(self._llm_label())
        self.query_one("#prompt", PromptInput).focus()

    def on_mount(self) -> None:
        self.console.push_theme(MARKDOWN_THEME)
        self.query_one(ConversationView).display = False
        self.query_one("#status", Static).display = False
        self.query_one("#prompt", PromptInput).focus()
        self._adapt_layout()
        self.set_interval(0.12, self._animate_status)

    def on_resize(self, event: events.Resize) -> None:
        self._adapt_layout(event.size)

    def _adapt_layout(self, size: Size | None = None) -> None:
        size = self.size if size is None else size
        compact = size.width < 70 or size.height < 25
        self.screen.set_class(compact, "compact")
        if self.is_mounted:
            self.query_one(WelcomeView).update_size(compact)

    def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        self._handle_submission(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._handle_submission(event.value)

    def _handle_submission(self, value: str) -> None:
        prompt = value.strip()
        if not prompt or self.busy:
            return

        # Slash commands handling
        if prompt.startswith("/"):
            self.query_one("#prompt", PromptInput).clear()
            self._handle_slash_command(prompt)
            return

        if self.workspace.root is None or not self.workspace.root.is_dir():
            self._set_status("请先通过 Ctrl+W 选择有效工作区", error=True)
            return

        self.query_one("#prompt", PromptInput).clear()
        self.busy = True
        self._started_at = monotonic()
        self._frame = 0
        self._append("You", prompt)
        self.query_one(ComposerView).set_running(True)
        self._animate_status()
        self.query_one(HeaderBar).update_agent_status("◌ 处理中")
        self._run_prompt(prompt)

    def _handle_slash_command(self, cmd: str) -> None:
        parts = cmd.split()
        command = parts[0].lower()
        if command in ("/help", "/?"):
            help_text = (
                "**快捷指令一览**\n\n"
                "- `/help`：显示此帮助信息\n"
                "- `/clear`：清空当前会话屏幕\n"
                "- `/workspace` 或 `/ws`：打开工作区管理器 (Ctrl+W)\n"
                "- `/settings` 或 `/model`：打开 LLM 模型与密钥配置\n"
                "- `/mode`：切换权限模式（需审批 / 完全访问）\n"
            )
            self._append("Trace", help_text)
        elif command == "/clear":
            self.transcript.clear()
            self._turn = 0
            conv = self.query_one(ConversationView)
            conv.clear()
            conv.display = False
            self.query_one(WelcomeView).display = True
            self.query_one("#shell").add_class("empty")
            self._set_status("")
        elif command in ("/workspace", "/ws"):
            self.action_workspaces()
        elif command in ("/settings", "/model", "/llm"):
            self.router.open_settings(self._settings_changed)
        elif command == "/mode":
            self.full_access = not self.full_access
            if self._external_agent is None:
                self.agent = SmolAgentRunner(
                    self.workspace,
                    approval=self._request_approval,
                    full_access=self.full_access,
                    config=self.llm_config,
                )
            self.query_one(HeaderBar).update_permission(self.full_access)
            self.notify(f"已切换权限模式：{'完全访问' if self.full_access else '需审批'}")
        else:
            self._set_status(f"未知指令 {command}，输入 /help 查看帮助", error=True)

    def _animate_status(self) -> None:
        if not self.busy:
            return
        frames = ("·", "✧", "✳", "✧")
        elapsed = monotonic() - self._started_at
        self._set_status(
            f"{frames[self._frame % len(frames)]}  正在处理  ·  {elapsed:.1f}s"
        )
        self.query_one(HeaderBar).update_agent_status(
            f"{frames[self._frame % len(frames)]} {elapsed:.1f}s"
        )
        self._frame += 1

    @work
    async def _run_prompt(self, prompt: str) -> None:
        try:
            if isinstance(self.agent, SmolAgentRunner):
                response = await asyncio.to_thread(
                    self.agent.run, prompt, self._agent_event
                )
            else:
                response = await asyncio.to_thread(self.agent.run, prompt)
        except Exception as error:  # noqa: BLE001 - keep the TUI alive for agent failures.
            self._append("Error", str(error))
            self._set_status("!  请求失败，可重新发送", error=True)
            self.query_one(HeaderBar).update_agent_status("! 异常")
        else:
            self._append("Agent", response)
            self._set_status("")
            self.query_one(HeaderBar).update_agent_status("● 就绪")
        finally:
            self.busy = False
            self.query_one(ComposerView).set_running(False)

    def _agent_event(self, event) -> None:
        """把后台 Agent 的规划、工具和观察事件送回 TUI 线程。"""
        self.call_from_thread(self._render_agent_event, event)

    def _render_agent_event(self, event) -> None:
        from smolagents.agents import ActionStep, FinalAnswerStep, PlanningStep
        from smolagents.models import ChatMessageStreamDelta

        conv = self.query_one(ConversationView)
        if isinstance(event, ChatMessageStreamDelta):
            if event.content:
                self._stream_thought += event.content
                conv.set_live_thought(self._stream_thought)
            return
        if isinstance(event, PlanningStep):
            self._flush_stream_thought()
            plan = event.plan.strip()
            if plan:
                self._append("Trace", f"规划\n{plan}")
            return
        if isinstance(event, ActionStep):
            self._flush_stream_thought()
            if event.observations:
                self._append("Tool", f"结果\n{event.observations}")
            return
        if isinstance(event, FinalAnswerStep):
            self._flush_stream_thought()
            self._append("Trace", "已生成最终回答")

    def _flush_stream_thought(self) -> None:
        content = self._stream_thought
        self._stream_thought = ""
        self.query_one(ConversationView).hide_live_thought()
        for marker in ("<code>", "```python", "```"):
            content = content.split(marker, 1)[0]
        content = content.replace("Thought:", "", 1).strip()
        if content:
            self._append("Trace", content)

    def _append(self, role: str, message: str) -> None:
        self.transcript.append(f"{role} > {message}")
        self.query_one("#shell").remove_class("empty")
        self.query_one(WelcomeView).display = False
        conv = self.query_one(ConversationView)
        conv.display = True

        if role == "You":
            self._turn += 1
            heading = format_user_turn_header(self._turn)
            body = format_timeline_body(message, prefix="  ", style=FG_PRIMARY)
        elif role == "Agent":
            elapsed = monotonic() - self._started_at if self.busy else None
            heading = format_agent_turn_header(elapsed)
            body = Markdown(message, code_theme=CODE_THEME, style=FG_PRIMARY)
        elif role == "Error":
            heading = format_error_header()
            body = format_timeline_body(message, prefix="  ", style=COLOR_DANGER)
        elif role == "Trace":
            heading = format_thought_header()
            body = format_timeline_body(message, prefix="│  ", style=FG_MUTED)
        elif role == "Tool":
            heading = format_tool_header("filesystem")
            body = format_timeline_body(message, prefix="│  ", style=FG_PRIMARY)
        else:
            heading = Text(f"[{role}]", style=f"bold {ACCENT_WARM}")
            body = Text(message, style=FG_PRIMARY)

        conv.write_entry(heading, body)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        conv = self.query_one(ConversationView)
        conv.set_status(message, error=error)
