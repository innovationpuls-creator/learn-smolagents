from pathlib import Path

from smolagents import CodeAgent, OpenAIModel
from smolagents.agents import FinalAnswerStep, RunResult
from smolagents.monitoring import LogLevel

from learn_smolagents.config import LLMConfig, SettingsStore
from learn_smolagents.permissions import FileAccess
from learn_smolagents.tools.filesystem import build_file_tools
from learn_smolagents.workspace import Workspace


class SmolAgentRunner:
    def __init__(
        self,
        workspace=None,
        *,
        approval=None,
        full_access=False,
        config: LLMConfig | None = None,
    ):
        self.config = config if config is not None else SettingsStore().load()
        self.workspace = workspace if workspace is not None else Workspace(Path.cwd())
        self.access = FileAccess(
            self.workspace, full_access=full_access, approval=approval
        )
        self._agent = None

    def _ensure_agent(self):
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
                verbosity_level=LogLevel.OFF,
                stream_outputs=True,
            )
        return self._agent

    def run(self, prompt, event_callback=None):
        agent = self._ensure_agent()
        if event_callback is None:
            result = agent.run(prompt, reset=False, return_full_result=True)
            return str(result.output if isinstance(result, RunResult) else result)
        result = None
        for event in agent.run(prompt, stream=True, reset=False):
            event_callback(event)
            if isinstance(event, (FinalAnswerStep, RunResult)):
                result = event.output
        return str(result)

    def reset_memory(self) -> None:
        """清空当前 Agent 的 smolagents 记忆，保留系统提示。"""
        if self._agent is not None:
            self._agent.memory.reset()

    def memory_steps(self) -> list[dict]:
        """返回 smolagents 提供的精简记忆步骤。"""
        return [] if self._agent is None else self._agent.memory.get_succinct_steps()
