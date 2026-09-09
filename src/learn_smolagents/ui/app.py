"""Warm, content-first terminal interface for the local CodeAgent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import ClassVar, Protocol, cast

from PIL import Image
from pygments.style import Style as PygmentsStyle
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    String,
    Token,
    _TokenType,
)
from resvg_py import svg_to_bytes
from rich.markdown import Markdown
from rich.syntax import PygmentsSyntaxTheme
from rich.text import Text
from rich.theme import Theme
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.geometry import Size
from textual.widgets import Button, Input, RichLog, Static

from learn_smolagents.agent import SmolAgentRunner
from learn_smolagents.config import SettingsStore
from learn_smolagents.ui.settings import SettingsScreen
from learn_smolagents.ui.approval import ApprovalScreen
from learn_smolagents.ui.workspaces import WorkspaceManager
from learn_smolagents.workspace import Workspace, WorkspaceStore

BACKGROUND = "#201e1b"
FOREGROUND = "#e8dfd1"
ACCENT = "#d99778"
MUTED = "#aaa093"


def render_mark(columns: int, rows: int) -> Text:
    """Rasterize the SVG into 2-by-4 dot cells, without blurred color blocks."""
    png = svg_to_bytes(
        svg_path=str(Path(__file__).parent.parent / "assets" / "smol-mark.svg"),
        width=columns * 2,
        height=rows * 4,
    )
    with Image.open(BytesIO(png)) as image:
        alpha = image.convert("RGBA").getchannel("A")
        dots = (
            (0, 0, 1),
            (0, 1, 2),
            (0, 2, 4),
            (1, 0, 8),
            (1, 1, 16),
            (1, 2, 32),
            (0, 3, 64),
            (1, 3, 128),
        )
        lines = []
        for row in range(rows):
            line = []
            for column in range(columns):

                def is_opaque(x: int, y: int) -> bool:
                    value = alpha.getpixel((x, y))
                    return isinstance(value, (int, float)) and value >= 64

                mask = sum(
                    bit for x, y, bit in dots if is_opaque(column * 2 + x, row * 4 + y)
                )
                line.append(chr(0x2800 + mask) if mask else " ")
            lines.append("".join(line))
    return Text("\n".join(lines), style=ACCENT)


class WarmCodeStyle(PygmentsStyle):
    """Code colors matched to the terminal palette."""

    background_color = "#292520"
    styles: ClassVar[Mapping[_TokenType, str]] = {
        Token: FOREGROUND,
        Comment: "italic #aaa093",
        Keyword: "bold #d99778",
        Name: FOREGROUND,
        Name.Function: "#d8bd93",
        Name.Builtin: "#d8bd93",
        Number: "#c3afce",
        Operator: "#c0b5a6",
        String: "#b8c39d",
    }


# Rich's Markdown annotation accepts a theme name, while its Syntax renderer
# also accepts the PygmentsSyntaxTheme instance used here at runtime.
CODE_THEME: str = cast(str, cast(object, PygmentsSyntaxTheme(WarmCodeStyle)))
MARKDOWN_THEME = Theme(
    {
        "markdown.h1": f"bold {FOREGROUND}",
        "markdown.h1.border": "#665449",
        "markdown.h2": f"bold {ACCENT}",
        "markdown.h3": f"bold {ACCENT}",
        "markdown.h4": f"bold {FOREGROUND}",
        "markdown.code": f"{ACCENT} on #292520",
        "markdown.code_block": FOREGROUND,
        "markdown.block_quote": MUTED,
        "markdown.list": ACCENT,
        "markdown.item.number": ACCENT,
        "markdown.link": "underline #d8bd93",
        "markdown.link_url": "underline #d8bd93",
        "markdown.table.border": "#665449",
        "markdown.table.header": f"bold {FOREGROUND}",
    }
)


class AgentRunner(Protocol):
    """The small interface the TUI needs from an Agent."""

    def run(self, prompt: str) -> str: ...


class LocalCodeAgentApp(App[None]):
    """A focused TUI for one local workspace and one Agent session."""

    TITLE = "Local CodeAgent"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "quit", "退出", show=False),
        Binding("ctrl+w", "workspaces", "工作区", show=False, priority=True),
    ]
    CSS = """
    Screen { background: #201e1b; color: #e8dfd1; align-horizontal: center; }
    #shell { width: 100%; max-width: 116; padding: 1 4; }
    #header { height: 4; border-bottom: solid #494139; margin-bottom: 1; }
    #identity { height: 1; }
    #brand { width: 1fr; color: #e8dfd1; text-style: bold; }
    #edition { width: auto; color: #aaa093; }
    #workspace-row { height: 1; margin-top: 1; }
    #permission-mode { height: 1; width: 18; min-width: 14; padding: 0; border: none; background: #393029; color: #d99778; }
    #workspace { height: 1; width: 1fr; color: #d99778; background: #393029;
        border: none; padding: 0 1; content-align: left middle; }
    #workspace:focus { text-style: bold; color: #e8dfd1; }
    Screen.compact #workspace-row { margin-top: 0; }
    #body { height: 1fr; }
    #welcome { height: 1fr; align: center middle; }
    #welcome-lockup { width: 70; max-width: 100%; height: 12; align-vertical: middle; }
    #sigil { height: 12; width: 24; margin-right: 4; }
    #welcome-copy { width: 1fr; height: 6; margin-top: 3; }
    #eyebrow { height: 2; color: #d99778; }
    #greeting { height: 2; text-style: bold; }
    #intro { height: 2; color: #aaa093; }
    #shell.empty { align-vertical: middle; }
    #shell.empty #header { dock: top; }
    #shell.empty #body { height: auto; }
    #shell.empty #welcome { height: 14; }
    #shell.empty #composer { margin-top: 1; }
    #shell.empty #help { margin-bottom: 2; }
    #conversation, #conversation:focus {
        height: 1fr; padding: 0 1; border: none;
        background: #201e1b; background-tint: transparent; color: #e8dfd1;
        overflow-x: hidden; overflow-y: auto;
        scrollbar-size-vertical: 0;
    }
    #live-thought { display: none; height: auto; max-height: 5; color: #aaa093; margin: 0 1; }
    #status { height: 1; color: #d99778; margin: 1 1 0 1; }
    #status.error { color: #e4a293; }
    #composer {
        height: 5; margin-top: 1; padding: 1 2;
        border: round #665449; background: #292520;
    }
    #composer:focus-within { border: round #d99778; }
    #composer.running { border: round #88705e; }
    #input-row { height: 1; }
    #prompt-mark { width: 3; color: #d99778; text-style: bold; }
    #prompt, #prompt:focus {
        height: 1; width: 1fr; padding: 0; border: none;
        background: #292520; background-tint: transparent; color: #e8dfd1;
    }
    #prompt > .input--placeholder { color: #aaa093; }
    #prompt > .input--cursor { background: #d99778; color: #201e1b; }
    #help { height: 1; color: #aaa093; margin: 0 1; }
    Screen.compact #shell { padding: 0 2; }
    Screen.compact #edition { display: none; }
    Screen.compact #header { height: 3; margin-bottom: 0; }
    Screen.compact #workspace { margin-top: 0; }
    Screen.compact #sigil { height: 6; width: 12; margin-right: 2; }
    Screen.compact #welcome-lockup { height: 6; }
    Screen.compact #welcome-copy { height: 5; margin-top: 1; }
    Screen.compact #eyebrow { height: 1; }
    Screen.compact #shell.empty #welcome { height: 6; }
    Screen.compact #shell.empty #help { margin-bottom: 0; }
    Screen.compact #intro { height: 1; }
    Screen.compact #greeting { height: 1; }
    Screen.compact #composer { height: 3; padding: 0 1; }
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
        self._approval_future = None
        self._external_agent = agent
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

    def compose(self) -> ComposeResult:
        with Vertical(id="shell", classes="empty"):
            with Vertical(id="header"):
                with Horizontal(id="identity"):
                    yield Static(
                        Text.assemble(("✳  ", ACCENT), "Local CodeAgent"), id="brand"
                    )
                    yield Static("S M O L A G E N T S", id="edition", markup=False)
                with Horizontal(id="workspace-row"):
                    directory = Button(
                        self._workspace_label(), id="workspace", compact=True
                    )
                    directory.tooltip = (
                        str(self.workspace.root)
                        if self.workspace.root
                        else "尚未选择工作区"
                    )
                    yield directory
                    yield Button("LLM 配置", id="llm-settings", compact=True)
                    yield Button("权限：需审批", id="permission-mode", compact=True)
            with Vertical(id="body"):
                with Vertical(id="welcome"), Horizontal(id="welcome-lockup"):
                    yield Static(render_mark(24, 12), id="sigil")
                    with Vertical(id="welcome-copy"):
                        yield Static("LOCAL / CODEAGENT", id="eyebrow", markup=False)
                        yield Static("从一个问题开始。", id="greeting", markup=False)
                        yield Static("输入消息，开始对话。", id="intro", markup=False)
                yield RichLog(id="conversation", wrap=True, markup=False, min_width=1)
                yield Static("", id="live-thought", markup=False)
                yield Static("", id="status", markup=False)
            with Vertical(id="composer"), Horizontal(id="input-row"):
                yield Static("❯", id="prompt-mark", markup=False)
                yield Input(placeholder="想聊些什么？", id="prompt", compact=True)
            yield Static("Enter 发送  ·  Ctrl+C 退出", id="help", markup=False)

    def _workspace_label(self) -> str:
        root = self.workspace.root
        return (
            f"📁  {root.name}  ·  {self.llm_config.model_id or '未配置模型'}"
            if root
            else "📁  尚未选择工作区"
        )

    def _request_approval(self, target, operation):
        return self.call_from_thread(self._show_approval, target, operation)

    async def _show_approval(self, target, operation):
        future = asyncio.get_running_loop().create_future()
        self._approval_future = future

        def answered(value):
            if not future.done():
                future.set_result(bool(value))

        await self.push_screen(ApprovalScreen(target, operation), answered)
        try:
            return await future
        finally:
            self._approval_future = None

    def on_unmount(self):
        if self._approval_future is not None and not self._approval_future.done():
            self._approval_future.set_result(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "llm-settings":
            if self.busy:
                self.notify("请等待当前请求结束后再修改 LLM 配置")
                return
            self.push_screen(
                SettingsScreen(self.settings_store), self._settings_changed
            )
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
            event.button.label = (
                "权限：完全访问" if self.full_access else "权限：需审批"
            )
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
        self.query_one("#conversation", RichLog).clear()
        self.query_one("#conversation").display = False
        self.query_one("#welcome").display = True
        self.query_one("#shell").add_class("empty")
        self.query_one("#workspace", Button).label = self._workspace_label()
        self._set_status("")
        self.query_one("#prompt", Input).focus()

    def action_workspaces(self) -> None:
        if isinstance(self.screen, WorkspaceManager):
            return
        if self.busy:
            self.notify("请等待当前请求结束后再管理工作区")
            return
        self.push_screen(
            WorkspaceManager(self.workspace_store), self._workspace_changed
        )

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
            log = self.query_one("#conversation", RichLog)
            log.clear()
            log.display = False
            self.query_one("#welcome").display = True
            self.query_one("#shell").add_class("empty")
            self._set_status("")
        directory = self.query_one("#workspace", Button)
        directory.label = self._workspace_label()
        directory.tooltip = (
            str(self.workspace.root) if self.workspace.root else "尚未选择工作区"
        )
        self.query_one("#prompt", Input).focus()

    def on_mount(self) -> None:
        self.console.push_theme(MARKDOWN_THEME)
        self.query_one("#status", Static).display = False
        self.query_one("#conversation", RichLog).display = False
        self.query_one("#prompt", Input).focus()
        self._adapt_layout()
        self.set_interval(0.12, self._animate_status)

    def on_resize(self, event: events.Resize) -> None:
        self._adapt_layout(event.size)

    def _adapt_layout(self, size: Size | None = None) -> None:
        size = self.size if size is None else size
        compact = size.width < 70 or size.height < 25
        self.screen.set_class(compact, "compact")
        if self.is_mounted:
            self.query_one("#sigil", Static).update(
                render_mark(12, 6) if compact else render_mark(24, 12)
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt or self.busy:
            return
        if self.workspace.root is None or not self.workspace.root.is_dir():
            self._set_status("请先通过 Ctrl+W 选择有效工作区", error=True)
            return
        self.busy = True
        self._started_at = monotonic()
        self._frame = 0
        event.input.clear()
        self._append("You", prompt)
        self.query_one("#composer").add_class("running")
        self._animate_status()
        self.query_one("#help", Static).update("处理中 · 可编辑下一条消息")
        self._run_prompt(prompt)

    def _animate_status(self) -> None:
        if not self.busy:
            return
        frames = ("·", "✧", "✳", "✧")
        elapsed = monotonic() - self._started_at
        self._set_status(
            f"{frames[self._frame % len(frames)]}  正在处理  ·  {elapsed:.1f}s"
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
        else:
            self._append("Agent", response)
            self._set_status("")
        finally:
            self.busy = False
            self.query_one("#composer").remove_class("running")
            self.query_one("#help", Static).update("Enter 发送  ·  Ctrl+C 退出")

    def _agent_event(self, event) -> None:
        """把后台 Agent 的规划、工具和观察事件送回 TUI 线程。"""
        self.call_from_thread(self._render_agent_event, event)

    def _render_agent_event(self, event) -> None:
        from smolagents.agents import ActionStep, FinalAnswerStep, PlanningStep
        from smolagents.models import ChatMessageStreamDelta

        if isinstance(event, ChatMessageStreamDelta):
            if event.content:
                self._stream_thought += event.content
                live = self.query_one("#live-thought", Static)
                live.update(f"◇ 思考\n{self._stream_thought}")
                live.display = True
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
        self.query_one("#live-thought", Static).display = False
        for marker in ("<code>", "```python", "```"):
            content = content.split(marker, 1)[0]
        content = content.replace("Thought:", "", 1).strip()
        if content:
            self._append("Trace", content)

    def _append(self, role: str, message: str) -> None:
        self.transcript.append(f"{role} > {message}")
        self.query_one("#shell").remove_class("empty")
        self.query_one("#welcome").display = False
        log = self.query_one("#conversation", RichLog)
        log.display = True
        if role == "You":
            self._turn += 1
        label, color = {
            "You": (f"❯  你  /  {self._turn:02d}", ACCENT),
            "Agent": ("✳  Agent", FOREGROUND),
            "Error": ("!  错误", "#e4a293"),
            "Trace": ("◇  思考", MUTED),
            "Tool": ("▸  工具", ACCENT),
        }[role]
        heading = Text(label, style=f"bold {color}")
        if role == "Agent" and self.busy:
            heading.append(f"  ·  {monotonic() - self._started_at:.1f}s", style=MUTED)
        log.write(heading)
        log.write(
            Markdown(message, code_theme=CODE_THEME, style=FOREGROUND)
            if role == "Agent"
            else Text(message, style=FOREGROUND)
        )
        log.write("")
        self.call_after_refresh(log.scroll_end, animate=False, x_axis=False)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        status = self.query_one("#status", Static)
        status.update(message)
        status.set_class(error, "error")
        status.display = bool(message)
