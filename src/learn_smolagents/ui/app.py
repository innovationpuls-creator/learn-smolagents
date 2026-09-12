"""Warm, refined, modular terminal interface for Local CodeAgent."""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable
from time import monotonic
from typing import Any, ClassVar, Protocol, cast

from rich.markdown import Markdown
from rich.text import Text
from smolagents.utils import AgentError, AgentParsingError
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.geometry import Size
from textual.widgets import Button, Input, Static

from learn_smolagents.agent import SmolAgentRunner
from learn_smolagents.config import SettingsStore
from learn_smolagents.ui.components import (
    ComposerView,
    ConversationView,
    HeaderBar,
    PromptInput,
    WelcomeView,
)
from learn_smolagents.ui.renderers import (
    extract_tool_arguments,
    render_error_card,
    render_plan_card,
    render_thought_card,
    render_tool_call_card,
    render_tool_result_card,
    try_parse_structured,
)
from learn_smolagents.ui.router import UIRouter
from learn_smolagents.ui.theme import (
    ACCENT_WARM,
    BACKGROUND,
    BG_BASE,
    CODE_THEME,
    FG_PRIMARY,
    MARKDOWN_THEME,
    format_agent_turn_header,
    format_timeline_body,
    format_user_turn_header,
)
from learn_smolagents.workspace import Workspace, WorkspaceStore

__all__ = ["BACKGROUND", "LocalCodeAgentApp"]


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
        self._total_tokens = 0
        self._rendered_step_numbers: set[int] = set()
        self._current_activity = ""
        self._activity_is_error = False
        self._pending_tool_calls = 0
        self._rendered_tool_results = 0
        self._last_tool_call: dict[str, Any] | None = None

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
            self.busy = False
            self._current_activity = ""
            self._pending_tool_calls = 0
            self._rendered_tool_results = 0
            interrupt = getattr(self.agent, "interrupt", None)
            if callable(interrupt):
                try:
                    interrupt()
                except Exception as error:  # noqa: BLE001 - keep cancellation failure visible.
                    self._append("Error", f"请求中断失败：{error}")
            for worker in self.workers:
                if not worker.is_finished:
                    worker.cancel()
            self.query_one(ComposerView).set_running(False)
            self.query_one(ConversationView).hide_live_thought()
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
            self.query_one(HeaderBar).update_permission(self.full_access)

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
        self._current_activity = "思考中"
        self._activity_is_error = False
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
                "- `/mode`：切换权限模式（工作区内允许、区外审批 / 完全访问）\n"
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
            self.notify(
                f"已切换权限模式：{'完全访问' if self.full_access else '工作区内允许、工作区外审批'}"
            )
        else:
            self._set_status(f"未知指令 {command}，输入 /help 查看帮助", error=True)

    def _animate_status(self) -> None:
        if not self.busy:
            return
        frames = ("·", "✧", "✳", "✧")
        elapsed = monotonic() - self._started_at
        label = (
            f"正在处理 · {self._current_activity}"
            if self._current_activity
            else "正在处理"
        )
        self._set_status(
            f"{frames[self._frame % len(frames)]}  {label}  ·  {elapsed:.1f}s",
            error=self._activity_is_error,
        )
        self.query_one(HeaderBar).update_agent_status(
            f"{frames[self._frame % len(frames)]} {elapsed:.1f}s"
        )
        self._frame += 1

    def _set_activity(self, activity: str, *, error: bool = False) -> None:
        self._current_activity = activity
        self._activity_is_error = error
        if self.busy:
            frames = ("·", "✧", "✳", "✧")
            elapsed = monotonic() - self._started_at
            label = f"正在处理 · {activity}" if activity else "正在处理"
            self._set_status(
                f"{frames[self._frame % len(frames)]}  {label}  ·  {elapsed:.1f}s",
                error=error,
            )
        else:
            self._set_status(activity, error=error)

    @work
    async def _run_prompt(self, prompt: str) -> None:
        self._total_tokens = 0
        self._rendered_step_numbers: set[int] = set()
        self._stream_thought = ""
        self._pending_tool_calls = 0
        self._rendered_tool_results = 0
        self._current_activity = "思考中"
        self._activity_is_error = False
        try:
            import inspect

            sig = inspect.signature(self.agent.run)
            if "event_callback" in sig.parameters or len(sig.parameters) > 1:
                streaming_run = cast(
                    Callable[[str, Callable[[Any], None]], str], self.agent.run
                )
                response = await asyncio.to_thread(
                    streaming_run, prompt, self._agent_event
                )
            else:
                response = await asyncio.to_thread(self.agent.run, prompt)

        except Exception as error:  # noqa: BLE001 - keep the TUI alive for agent failures.
            self._flush_stream_thought()
            self.query_one(ConversationView).hide_live_thought()
            self._append("Error", str(error))
            self._set_activity("!  请求失败，可重新发送", error=True)
            self.query_one(HeaderBar).update_agent_status("! 异常")
        else:
            self._flush_stream_thought()
            self.query_one(ConversationView).hide_live_thought()
            self._append("Agent", response)
            result = getattr(self.agent, "last_result", None)
            if result is not None and result.state != "success":
                self._append(
                    "Error", "已达到最大执行步数；以上为兜底总结，本轮未正常完成。"
                )
                self._set_status("! 达到执行步数上限", error=True)
                self.query_one(HeaderBar).update_agent_status("! 未完成")
            else:
                self._set_status("")
                self.query_one(HeaderBar).update_agent_status("● 就绪")
            self._current_activity = ""
        finally:
            self.busy = False
            self._current_activity = ""
            self.query_one(ComposerView).set_running(False)

    def _agent_event(self, event: Any) -> None:
        """把后台 Agent 的规划、工具和观察事件送回 TUI 线程。"""
        self.call_from_thread(self._render_agent_event, event)

    @staticmethod
    def _split_thought_and_code(raw: str) -> tuple[str, str, bool]:
        """Separate thought text and code blocks from streaming LLM output."""
        markers = [
            "<code>",
            "```python",
            "```py\n",
            "```py ",
            "```",
            "<action>",
            "Action:",
        ]
        earliest_idx = -1
        found_marker = ""
        for m in markers:
            idx = raw.find(m)
            if idx != -1 and (earliest_idx == -1 or idx < earliest_idx):
                earliest_idx = idx
                found_marker = m

        if earliest_idx == -1:
            thought = raw
            code = ""
            has_code = False
        else:
            thought = raw[:earliest_idx]
            code = raw[earliest_idx + len(found_marker) :]
            has_code = True

        thought = thought.strip()
        for prefix in ("Thought:", "Thoughts:", "思考：", "思考:"):
            if thought.startswith(prefix):
                thought = thought[len(prefix) :].strip()
                break
        return thought, code.strip(), has_code

    @staticmethod
    def _detect_tool_name(tool_call: Any, extra_tools: set[str] | None = None) -> str:
        """Use the native event identity, never infer executed tools from source text."""
        return str(getattr(tool_call, "name", "tool"))

    @staticmethod
    def _is_pure_final_answer(code: str) -> bool:
        """Check whether a python action snippet is solely delivering the final answer."""
        cleaned = code.strip()
        if not cleaned or "final_answer" not in cleaned:
            return False

        try:
            tree = ast.parse(cleaned)
        except SyntaxError:
            return False

        # Only hide a literal delivery. Resolving aliases, subscripts, nested calls
        # or assignments would require interpreter state; show those native actions.
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
            return False
        call = tree.body[0].value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "final_answer"
        ):
            return False
        if any(keyword.arg is None for keyword in call.keywords):
            return False
        try:
            for value in [*call.args, *(keyword.value for keyword in call.keywords)]:
                ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            return False
        return True

    @staticmethod
    def _clean_action_step_observation(raw: str, max_lines: int | None = 30) -> str:
        """Format smolagents ActionStep observations cleanly, removing wrapper boilerplate."""
        if not raw:
            return ""
        logs = ""
        last_output = ""
        if "Last output from code snippet:" in raw:
            parts = raw.split("Last output from code snippet:", 1)
            logs_part = parts[0]
            output_part = parts[1].strip()
            if "Execution logs:" in logs_part:
                logs = logs_part.replace("Execution logs:", "", 1).strip()
            else:
                logs = logs_part.strip()
            if output_part != "None":
                last_output = output_part
        else:
            if "Execution logs:" in raw:
                logs = raw.replace("Execution logs:", "", 1).strip()
            else:
                logs = raw.strip()

        if logs and last_output:
            cleaned = f"{logs}\n\n-> {last_output}"
        elif logs:
            cleaned = logs
        elif last_output:
            cleaned = last_output
        else:
            cleaned = "执行完成（无输出）"

        return LocalCodeAgentApp._preview_observation(cleaned, max_lines)

    @staticmethod
    def _preview_observation(cleaned: str, max_lines: int | None = 30) -> str:
        """Limit the display without reinterpreting or changing native observations."""
        cleaned_stripped = cleaned.strip()
        is_structured = (
            cleaned_stripped.startswith("{") and cleaned_stripped.endswith("}")
        ) or (cleaned_stripped.startswith("[") and cleaned_stripped.endswith("]"))
        if not is_structured:
            parsed, _ = try_parse_structured(cleaned)
            is_structured = parsed is not None

        if not is_structured:
            lines = cleaned.splitlines()
            if max_lines is not None and len(lines) > max_lines:
                truncated = lines[:max_lines]
                truncated.append(
                    f"... (界面省略其余 {len(lines) - max_lines} 行输出；模型观察不受此显示限制) ..."
                )
                return "\n".join(truncated)
        return cleaned

    def _render_agent_event(self, event: Any) -> None:
        if not self.busy:
            return

        from smolagents.agents import (
            ActionOutput,
            ActionStep,
            FinalAnswerStep,
            PlanningStep,
            ToolCall,
            ToolOutput,
        )
        from smolagents.models import ChatMessageStreamDelta

        conv = self.query_one(ConversationView)

        # 1. ChatMessageStreamDelta: token-by-token streaming
        if isinstance(event, ChatMessageStreamDelta):
            if event.content:
                self._stream_thought += event.content
                thought, _, has_code = self._split_thought_and_code(
                    self._stream_thought
                )
                if thought:
                    conv.set_live_thought(thought)
                if has_code:
                    self._set_activity("正在生成执行代码...")
            return

        # 2. PlanningStep: high-level task plan generated
        if isinstance(event, PlanningStep):
            # The streaming tokens for planning were shown in live-thought;
            # clear them so they are not flushed as a duplicate thought card.
            self._stream_thought = ""
            conv.hide_live_thought()

            if getattr(event, "token_usage", None):
                self._total_tokens += getattr(event.token_usage, "total_tokens", 0) or 0

            plan = (event.plan or "").strip()
            if plan:
                duration = (
                    getattr(event.timing, "duration", None)
                    if hasattr(event, "timing")
                    else None
                )
                self._append_plan(plan, duration=duration)
            self._set_activity("计划已制定，开始执行任务...")
            return

        # 3. ToolCall: tool or code action planned, BEFORE execution starts
        if isinstance(event, ToolCall):
            self._flush_stream_thought()

            tool_name = self._detect_tool_name(event)
            args_str = str(event.arguments or "").strip()

            # If ToolCallingAgent calls final_answer tool, or CodeAgent runs pure final answer
            if tool_name == "final_answer" or (
                getattr(event, "name", "") == "python_interpreter"
                and self._is_pure_final_answer(args_str)
            ):
                self._set_activity("正在组织最终回答...")
                return

            self._pending_tool_calls += 1
            self._append_tool_call(tool_name, args_str)
            self._set_activity(f"正在执行: {tool_name}...")
            return

        # 4. ToolOutput: tool execution output (from ToolCallingAgent)
        if isinstance(event, ToolOutput):
            if getattr(event, "is_final_answer", False):
                self._set_activity("正在整理最终回答...")
                return
            obs = getattr(event, "observation", None)
            if obs is None:
                obs = getattr(event, "output", "")
            clean_obs = self._clean_action_step_observation(
                str(obs or ""), max_lines=None
            )
            if clean_obs:
                self._append_tool_result(clean_obs, is_error=False)
                self._rendered_tool_results += 1
                if self._pending_tool_calls > 0:
                    self._pending_tool_calls -= 1
                self._set_activity("工具执行完成，分析结果中...")
            return

        # 5. ActionOutput: execution output flag
        if isinstance(event, ActionOutput):
            if event.is_final_answer:
                self._set_activity("正在整理最终回答...")
            return

        # 6. ActionStep: step finalized with execution output, timing, token usage, errors
        if isinstance(event, ActionStep):
            # Native max-step exhaustion may re-yield the preceding ActionStep.
            if event.step_number in self._rendered_step_numbers:
                return
            self._rendered_step_numbers.add(event.step_number)
            self._flush_stream_thought()

            if getattr(event, "token_usage", None):
                self._total_tokens += getattr(event.token_usage, "total_tokens", 0) or 0

            # Check if this step was user-interrupted
            if getattr(event, "error", None) is not None:
                err_msg = str(event.error)
                if type(event.error) is AgentError and err_msg == "Agent interrupted.":
                    return

                if isinstance(event.error, AgentParsingError):
                    self._append(
                        "Trace",
                        "回答格式不符合执行协议，本步骤未执行代码；Agent 将按原生流程尝试恢复。",
                    )
                    self._set_activity("回答格式错误，等待恢复...", error=False)
                    self._pending_tool_calls = 0
                    self._rendered_tool_results = 0
                    return

                duration = (
                    getattr(event.timing, "duration", None)
                    if hasattr(event, "timing")
                    else None
                )
                # A native step can have completed side effects before failing.
                # Keep its observation before the error, without duplicating outputs
                # already delivered as ToolOutput events.
                raw_obs = event.observations or ""
                if self._rendered_tool_results == 0 and raw_obs.strip():
                    clean_obs = self._clean_action_step_observation(
                        raw_obs, max_lines=None
                    )
                    if clean_obs:
                        self._append_tool_result(clean_obs)
                self._append_tool_result(err_msg, duration=duration, is_error=True)
                self._set_activity(f"! 工具执行遇到问题: {err_msg[:40]}", error=True)
                self._pending_tool_calls = 0
                self._rendered_tool_results = 0
                return

            # Skip observation card if pure final answer and no tool calls were rendered
            if (
                getattr(event, "is_final_answer", False)
                and self._pending_tool_calls == 0
                and self._rendered_tool_results == 0
            ):
                return

            # Only render observation if not already rendered by ToolOutput
            if self._rendered_tool_results == 0:
                duration = (
                    getattr(event.timing, "duration", None)
                    if hasattr(event, "timing")
                    else None
                )
                raw_obs = getattr(event, "observations", "") or ""
                clean_obs = self._clean_action_step_observation(raw_obs, max_lines=None)
                if clean_obs:
                    self._append_tool_result(
                        clean_obs, duration=duration, is_error=False
                    )
                    self._set_activity("工具执行完成，分析结果中...")

            self._pending_tool_calls = 0
            self._rendered_tool_results = 0
            return

        # 7. FinalAnswerStep: agent completed task
        if isinstance(event, FinalAnswerStep):
            self._flush_stream_thought()
            conv.hide_live_thought()
            self._set_activity("回答生成完成")
            return

    def _flush_stream_thought(self) -> None:
        raw = self._stream_thought
        self._stream_thought = ""
        self.query_one(ConversationView).hide_live_thought()
        if not raw:
            return
        thought, _, _ = self._split_thought_and_code(raw)
        if thought:
            self._append_thought(thought)

    def _append_thought(self, thought: str, duration: float | None = None) -> None:
        self.transcript.append(f"Trace > {thought}")
        self.query_one("#shell").remove_class("empty")
        self.query_one(WelcomeView).display = False
        conv = self.query_one(ConversationView)
        conv.display = True
        panel = render_thought_card(thought, duration=duration)
        conv.write_entry(panel)

    def _append_plan(self, plan: str, duration: float | None = None) -> None:
        self.transcript.append(f"Trace > 规划\n{plan}")
        self.query_one("#shell").remove_class("empty")
        self.query_one(WelcomeView).display = False
        conv = self.query_one(ConversationView)
        conv.display = True
        panel = render_plan_card(plan, duration=duration)
        conv.write_entry(panel)

    def _append_tool_call(self, tool_name: str, code_or_args: str) -> None:
        self.transcript.append(f"Tool > 调用 [{tool_name}]\n{code_or_args}")
        self.query_one("#shell").remove_class("empty")
        self.query_one(WelcomeView).display = False
        conv = self.query_one(ConversationView)
        conv.display = True
        self._last_tool_call = {
            "tool_name": tool_name,
            "code_or_args": code_or_args,
            "extracted_args": extract_tool_arguments(tool_name, code_or_args),
        }
        panel = render_tool_call_card(tool_name, code_or_args)
        conv.write_entry(panel)

    def _append_tool_result(
        self, observation: str, duration: float | None = None, is_error: bool = False
    ) -> None:
        self.transcript.append(
            f"Tool > {'错误' if is_error else '结果'}\n{observation}"
        )
        self.query_one("#shell").remove_class("empty")
        self.query_one(WelcomeView).display = False
        conv = self.query_one(ConversationView)
        conv.display = True
        tool_ctx = getattr(self, "_last_tool_call", None)
        panel = render_tool_result_card(
            self._preview_observation(observation) if not is_error else observation,
            duration=duration,
            is_error=is_error,
            tool_context=tool_ctx,
            workspace_root=self.workspace.root,
        )
        conv.write_entry(panel)

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
            conv.write_entry(heading, body)
        elif role == "Agent":
            elapsed = monotonic() - self._started_at if self.busy else None
            tokens = getattr(self, "_total_tokens", 0)
            result = getattr(self.agent, "last_result", None)
            if result is not None:
                tokens = result.token_usage.total_tokens if result.token_usage else 0
                elapsed = result.timing.duration
            heading = format_agent_turn_header(
                elapsed, tokens=tokens if tokens > 0 else None
            )
            body = Markdown(message, code_theme=CODE_THEME, style=FG_PRIMARY)
            conv.write_entry(heading, body)
        elif role == "Error":
            panel = render_error_card(message)
            conv.write_entry(panel)
        elif role == "Trace":
            panel = render_thought_card(message)
            conv.write_entry(panel)
        elif role == "Tool":
            panel = render_tool_result_card(message, workspace_root=self.workspace.root)
            conv.write_entry(panel)
        else:
            heading = Text(f"[{role}]", style=f"bold {ACCENT_WARM}")
            body = Text(message, style=FG_PRIMARY)
            conv.write_entry(heading, body)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        conv = self.query_one(ConversationView)
        conv.set_status(message, error=error)
