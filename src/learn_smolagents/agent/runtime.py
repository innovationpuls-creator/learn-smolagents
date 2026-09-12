import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast

from smolagents import CodeAgent, OpenAIModel
from smolagents.agents import (
    ActionOutput,
    ActionStep,
    AgentError,
    AgentExecutionError,
    AgentGenerationError,
    AgentMaxStepsError,
    FinalAnswerStep,
    PlanningStep,
    RunResult,
    StreamEvent,
    Timing,
    TokenUsage,
    ToolCall,
    ToolOutput,
)
from smolagents.models import ChatMessageStreamDelta
from smolagents.monitoring import LogLevel

from learn_smolagents.config import LLMConfig, SettingsStore
from learn_smolagents.permissions import FileAccess
from learn_smolagents.tools.filesystem import build_file_tools
from learn_smolagents.workspace import Workspace

__all__ = [
    "ActionOutput",
    "ActionStep",
    "AgentError",
    "AgentExecutionError",
    "AgentGenerationError",
    "ChatMessageStreamDelta",
    "FinalAnswerStep",
    "PlanningStep",
    "RunResult",
    "SmolAgentRunner",
    "Timing",
    "TokenUsage",
    "ToolCall",
    "ToolOutput",
]


AGENT_SYSTEM_PROMPT_CONSTRAINTS = """
执行约束：
- 只导入系统提示列出的 authorized imports。文件操作使用上文注册的文件工具，
  不要导入系统模块绕过工具；解释器拒绝的操作应改用已有工具。
- 每次行动遵循上文规定的代码标签与 Python 协议。最终回答也必须通过
  final_answer 交付，不能以代码块外的纯文本代替。
- 查看项目结构优先 list_directory(recursive=True)，遵循返回的范围和省略信息。
  仅在缺少决策所需信息时继续读取；复用本轮观察，避免重复遍历和打印整棵目录树。
- 完整清点需要 include_ignored=True 并检查 depth_limited；项目概览不是完整清单。
  确定需删除整个目录时使用 delete_directory(recursive=True)，不必自行逐文件递归。
  清空工作区使用 directory_path="."，保留根目录；操作后按任务范围核验结果。
- 观察被截断时不能当作完整结果，应缩小查询范围或只打印所需摘要。
"""


class SmolAgentRunner:
    def __init__(
        self,
        workspace: Workspace | None = None,
        *,
        approval: Any = None,
        full_access: bool = False,
        config: LLMConfig | None = None,
    ):
        self.config = config if config is not None else SettingsStore().load()
        self.workspace = workspace if workspace is not None else Workspace(Path.cwd())
        self.access = FileAccess(
            self.workspace, full_access=full_access, approval=approval
        )
        self._agent = None
        self._last_result: RunResult | None = None

    def _ensure_agent(self) -> CodeAgent:
        if self._agent is None:
            self.config.validate()
            file_tools = build_file_tools(self.access)

            self._agent = CodeAgent(
                model=OpenAIModel(
                    model_id=self.config.model_id,
                    api_base=self.config.api_base,
                    api_key=self.config.api_key,
                ),
                tools=file_tools,
                instructions=AGENT_SYSTEM_PROMPT_CONSTRAINTS,
                verbosity_level=LogLevel.OFF,
                stream_outputs=True,
            )
        return self._agent

    def run(
        self, prompt: str, event_callback: Callable[[Any], None] | None = None
    ) -> str:
        agent = self._ensure_agent()
        self._last_result = None
        run_start_time = time.time()
        # Native full results include all memory when reset=False. Scope accounting
        # to this run without clearing conversational or interpreter state.
        memory = getattr(agent, "memory", None)
        start_index = len(memory.steps) if memory is not None else 0
        if event_callback is None:
            native_result = agent.run(prompt, reset=False, return_full_result=True)
            result = (
                native_result.output
                if isinstance(native_result, RunResult)
                else native_result
            )
        else:
            result = None
            completed = False
            stream = cast(
                Iterable[StreamEvent], agent.run(prompt, stream=True, reset=False)
            )
            for event in stream:
                event_callback(event)
                if isinstance(event, FinalAnswerStep):
                    result = event.output
                    completed = True
            if not completed:
                raise RuntimeError("Agent 未返回 FinalAnswerStep，无法确认本轮完成")

        current_steps = memory.steps[start_index:] if memory is not None else []
        measured_steps = [
            step
            for step in current_steps
            if isinstance(step, (ActionStep, PlanningStep))
        ]
        # Match native unknown-usage semantics; include planning and the max-step
        # fallback, which are not reliably represented by Monitor or stream events.
        token_usage = None
        usages = [
            step.token_usage for step in measured_steps if step.token_usage is not None
        ]
        if measured_steps and len(usages) == len(measured_steps):
            token_usage = TokenUsage(
                input_tokens=sum(usage.input_tokens for usage in usages),
                output_tokens=sum(usage.output_tokens for usage in usages),
            )
        state = (
            "max_steps_error"
            if current_steps
            and isinstance(
                getattr(current_steps[-1], "error", None), AgentMaxStepsError
            )
            else "success"
        )
        self._last_result = RunResult(
            output=result,
            token_usage=token_usage,
            steps=[step.dict() for step in current_steps],
            timing=Timing(start_time=run_start_time, end_time=time.time()),
            state=state,
        )
        return str(result if result is not None else "")

    def interrupt(self) -> None:
        """中断正在运行的 Agent 任务。"""
        if self._agent is not None:
            if hasattr(self._agent, "interrupt") and callable(self._agent.interrupt):
                self._agent.interrupt()
            else:
                self._agent.interrupt_switch = True

    def reset_memory(self) -> None:
        """清空当前 Agent 的 smolagents 记忆，保留系统提示。"""
        if self._agent is not None:
            self._agent.memory.reset()
            if hasattr(self._agent, "monitor") and hasattr(
                self._agent.monitor, "reset"
            ):
                self._agent.monitor.reset()
            self._last_result = None

    def memory_steps(self) -> list[dict[str, Any]]:
        """返回 smolagents 提供的精简记忆步骤。"""
        return [] if self._agent is None else self._agent.memory.get_succinct_steps()

    @property
    def last_result(self) -> RunResult | None:
        """获取最近一次运行的 RunResult 详情（含 Timing 与 TokenUsage）。"""
        return self._last_result
