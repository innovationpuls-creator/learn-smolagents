"""Exercise the real CodeAgent, local interpreter and UI without network access."""

from pathlib import Path

import pytest
from rich.console import Console
from smolagents.agents import (
    ActionStep,
    FinalAnswerStep,
    PlanningStep,
    Timing,
    TokenUsage,
    ToolCall,
)
from smolagents.models import ChatMessage, ChatMessageStreamDelta, Model
from smolagents.utils import AgentExecutionError, AgentMaxStepsError, AgentParsingError

from learn_smolagents.agent import runtime
from learn_smolagents.config import LLMConfig
from learn_smolagents.permissions import FileAccess
from learn_smolagents.tools.filesystem import build_file_tools
from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.components import PromptInput
from learn_smolagents.ui.renderers import render_directory_tree, render_tool_result_card
from learn_smolagents.workspace import Workspace


class ScriptedModel(Model):
    def __init__(self, replies):
        super().__init__(model_id="local-test")
        self.replies = iter(replies)
        self.messages = []

    def generate(self, messages, **kwargs):
        self.messages.append(messages)
        content, usage = next(self.replies)
        return ChatMessage(role="assistant", content=content, token_usage=usage)

    def generate_stream(self, messages, **kwargs):
        message = self.generate(messages, **kwargs)
        yield ChatMessageStreamDelta(
            content=message.content, token_usage=message.token_usage
        )


def runner_for(monkeypatch, tmp_path, replies):
    model = ScriptedModel(replies)
    monkeypatch.setattr(runtime, "OpenAIModel", lambda **kwargs: model)
    runner = runtime.SmolAgentRunner(
        workspace=Workspace(tmp_path),
        config=LLMConfig("test", "https://example.com", "unused"),
    )
    return runner, model


@pytest.mark.parametrize("stream", [False, True])
def test_native_recovery_and_per_turn_usage(monkeypatch, tmp_path, stream):
    runner, model = runner_for(
        monkeypatch,
        tmp_path,
        [
            ("<code>import os</code>", TokenUsage(10, 2)),
            ("已经完成。", TokenUsage(20, 3)),
            (
                "<code>create_file('result.txt', 'saved')\nfinal_answer('done')</code>",
                TokenUsage(30, 4),
            ),
            ("<code>final_answer(read_file('result.txt'))</code>", TokenUsage(7, 1)),
        ],
    )
    events = []
    assert runner.run("create result", events.append if stream else None) == "done"
    assert (tmp_path / "result.txt").read_text() == "saved"
    first = runner.last_result
    assert first.state == "success"
    assert first.token_usage.total_tokens == 69
    errors = [
        step.error
        for step in runner._agent.memory.steps
        if isinstance(step, ActionStep)
    ]
    assert isinstance(errors[0], AgentExecutionError)
    assert isinstance(errors[1], AgentParsingError)
    assert errors[2] is None
    assert runner.run("read result", events.append if stream else None) == "saved"
    assert runner.last_result.token_usage.total_tokens == 8
    assert (
        len(runner.last_result.steps) == 2
    )  # TaskStep + ActionStep, not historical steps
    assert len(runner._agent.memory.steps) == 6
    assert "create result" in str(model.messages[-1])
    agent = runner._agent
    assert agent.instructions in agent.system_prompt
    assert str(agent.authorized_imports) in agent.system_prompt
    assert all(tag in agent.system_prompt for tag in agent.code_block_tags)
    if stream:
        assert isinstance(events[-1], FinalAnswerStep)


@pytest.mark.parametrize("stream", [False, True])
def test_native_max_steps_preserves_failure_and_fallback_usage(
    monkeypatch, tmp_path, stream
):
    runner, _ = runner_for(
        monkeypatch,
        tmp_path,
        [
            ("no code", TokenUsage(10, 2)),
            ("fallback summary", TokenUsage(20, 3)),
        ],
    )
    runner._ensure_agent().max_steps = 1
    assert (
        runner.run("task", (lambda event: None) if stream else None)
        == "fallback summary"
    )
    assert runner.last_result.state == "max_steps_error"
    assert runner.last_result.token_usage.total_tokens == 35
    assert isinstance(runner._agent.memory.steps[-1].error, AgentMaxStepsError)


def test_missing_usage_stays_unknown(monkeypatch, tmp_path):
    runner, _ = runner_for(
        monkeypatch, tmp_path, [("<code>final_answer('done')</code>", None)]
    )
    runner._ensure_agent().stream_outputs = False
    runner.run("task")
    assert runner.last_result.token_usage is None


def test_native_planning_usage_counted_once(monkeypatch, tmp_path):
    runner, _ = runner_for(
        monkeypatch,
        tmp_path,
        [
            ("Plan: return result", TokenUsage(10, 2)),
            ("<code>final_answer('done')</code>", TokenUsage(20, 3)),
        ],
    )
    runner._ensure_agent().planning_interval = 1
    events = []
    runner.run("task", events.append)
    assert any(isinstance(event, PlanningStep) for event in events)
    assert runner.last_result.token_usage.total_tokens == 35


def test_native_template_failure_is_not_silently_ignored(monkeypatch, tmp_path):
    runner, _ = runner_for(monkeypatch, tmp_path, [])

    def fail(*args, **kwargs):
        raise OSError("template unavailable")

    monkeypatch.setattr("smolagents.agents.importlib.resources.files", fail)
    with pytest.raises(OSError, match="template unavailable"):
        runner._ensure_agent()
    assert runner._agent is None


def test_recursive_scope_links_and_deletion(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (root / "source").mkdir()
    (root / "source" / "nested").mkdir()
    (root / "source" / "nested" / "app.py").write_text("x")
    for name in ("target", ".mvn", ".git"):
        (root / name).mkdir()
        (root / name / "data").write_text("x")
    (root / "alias").symlink_to(outside, target_is_directory=True)
    (root / "file-link").symlink_to(outside / "keep.txt")
    (root / "broken").symlink_to(outside / "missing")
    tools = {t.name: t for t in build_file_tools(FileAccess(Workspace(root)))}
    overview = tools["list_directory"](".", recursive=True, max_depth=1)
    assert set(overview["skipped"]) == {
        str(root / n) for n in ("target", ".mvn", ".git")
    }
    assert overview["depth_limited"] == [str(root / "source")]
    full = tools["list_directory"](
        ".", recursive=True, max_depth=3, include_ignored=True
    )
    assert full["skipped"] == full["depth_limited"] == []
    assert str(root / "target" / "data") in [i["path"] for i in full["items"]]
    links = [i for i in full["items"] if i["type"] == "symlink"]
    assert {Path(i["path"]).name for i in links} == {"alias", "file-link", "broken"}
    assert not any(str(outside) in i["path"] for i in full["items"])
    for link in links:
        with pytest.raises(ValueError, match="符号链接"):
            tools["delete_file"](link["path"])
        with pytest.raises(ValueError, match="符号链接"):
            tools["delete_directory"](link["path"], recursive=True)
    with pytest.raises(ValueError, match="max_depth"):
        tools["list_directory"](".", recursive=True, max_depth=0)
    result = tools["delete_directory"](".", recursive=True)
    assert result["cleared_workspace_root"]
    assert root.is_dir() and not list(root.iterdir())
    assert (outside / "keep.txt").read_text() == "keep"


def test_registered_recursive_tools_execute_in_native_interpreter(
    monkeypatch, tmp_path
):
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "build.txt").write_text("build")
    runner, _ = runner_for(
        monkeypatch,
        tmp_path,
        [
            (
                "<code>print(list_directory('.', recursive=True, include_ignored=True))</code>",
                TokenUsage(1, 1),
            ),
            (
                "<code>delete_directory('.', recursive=True)\nfinal_answer(list_directory('.'))</code>",
                TokenUsage(1, 1),
            ),
        ],
    )
    runner.run("清空工作区", lambda event: None)
    assert not list(tmp_path.iterdir())
    assert runner.last_result.state == "success"
    assert (
        len([s for s in runner._agent.memory.steps if isinstance(s, ActionStep)]) == 2
    )


@pytest.mark.asyncio
async def test_ui_keeps_recovery_failure_state_and_complete_observation(
    monkeypatch, tmp_path
):
    runner, _ = runner_for(
        monkeypatch,
        tmp_path,
        [
            ("no code", TokenUsage(1, 2)),
            ("fallback", TokenUsage(3, 4)),
        ],
    )
    runner._ensure_agent().max_steps = 1
    app = LocalCodeAgentApp(agent=runner)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "task"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert sum("本步骤未执行代码" in e for e in app.transcript) == 1
        assert any("本轮未正常完成" in e for e in app.transcript)
        assert "max_steps_error" == runner.last_result.state
        app.busy = True
        raw = "\n".join(f"line {i}" for i in range(100))
        app._render_agent_event(
            ActionStep(
                step_number=2,
                timing=Timing(0, 1),
                observations="Execution logs:\n" + raw,
            )
        )
        assert "line 99" in app.transcript[-1]
        preview = app._clean_action_step_observation(raw)
        assert "界面省略" in preview and "line 99" not in preview
        # Similar wording from an unrelated execution error must not be suppressed.
        app._render_agent_event(
            ActionStep(
                step_number=3,
                timing=Timing(0, 1),
                error=ValueError("regex pattern missing"),
            )
        )
        assert "regex pattern missing" in app.transcript[-1]


def test_model_observation_uses_native_output_limit(monkeypatch, tmp_path):
    runner, model = runner_for(
        monkeypatch,
        tmp_path,
        [
            ("<code>print('A' * 5000)</code>", TokenUsage(1, 1)),
            ("<code>final_answer('done')</code>", TokenUsage(1, 1)),
        ],
    )
    agent = runner._ensure_agent()
    agent.python_executor.max_print_outputs_length = 1000
    runner.run("task", lambda event: None)
    observation = next(
        s.observations for s in agent.memory.steps if isinstance(s, ActionStep)
    )
    assert "truncated" in observation and "1000 characters" in observation
    assert "truncated" in str(model.messages[-1])


def test_python_identity_and_rendered_scope():
    code = "list_directory('.')\ndelete_file('file.txt')"
    call = ToolCall(name="python_interpreter", arguments=code, id="x")
    assert LocalCodeAgentApp._detect_tool_name(call) == "python_interpreter"
    assert not LocalCodeAgentApp._is_pure_final_answer(
        "cleanup()\nfinal_answer('done')"
    )
    console = Console(width=100, record=True)
    console.print(render_tool_result_card("done", duration=1.2))
    console.print(
        render_directory_tree(
            {
                "items": [{"path": "alias", "type": "symlink"}],
                "skipped": ["target"],
                "depth_limited": ["src"],
            }
        )
    )
    text = console.export_text()
    assert "步骤耗时" in text and "符号链接" in text
    assert "概览忽略" in text and "达到深度上限" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(132, 39), (48, 26)])
async def test_permission_scope_label_fits_header(size):
    from rich.cells import cell_len
    from textual.widgets import Button

    app = LocalCodeAgentApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        button = app.query_one("#permission-mode", Button)
        assert "区外审批" in str(button.label)
        assert cell_len(str(button.label)) <= button.content_region.width
        assert "工作区内允许读写和删除" in str(button.tooltip)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "final_answer([delete_file][0]('victim.txt'))",
        "final_answer({'remove': delete_file}['remove']('victim.txt'))",
        "remove = delete_file\nfinal_answer(remove('victim.txt'))",
    ],
)
async def test_indirect_delete_preserves_native_action_and_observation(
    monkeypatch, tmp_path, code
):
    victim = tmp_path / "victim.txt"
    victim.write_text("fixture")
    runner, _ = runner_for(
        monkeypatch, tmp_path, [(f"<code>{code}</code>", TokenUsage(1, 1))]
    )
    app = LocalCodeAgentApp(agent=runner)
    async with app.run_test() as pilot:
        app.query_one("#prompt", PromptInput).value = "delete fixture"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert not victim.exists()
        assert runner.last_result.state == "success"
        call = next(
            i
            for i, text in enumerate(app.transcript)
            if "Tool > 调用 [python_interpreter]" in text
        )
        observation = next(
            i
            for i, text in enumerate(app.transcript)
            if "Tool > 结果" in text and "deleted" in text
        )
        answer = next(
            i for i, text in enumerate(app.transcript) if text.startswith("Agent >")
        )
        assert call < observation < answer


@pytest.mark.parametrize(
    "code",
    [
        "final_answer(str(delete_file('victim.txt')))",
        "str = delete_file\nfinal_answer(str('victim.txt'))",
        "final_answer((lambda: delete_file)()('victim.txt'))",
        "final_answer(**payload)",
        "final_answer(result)",
    ],
)
def test_nonliteral_answer_code_is_not_hidden(code):
    assert not LocalCodeAgentApp._is_pure_final_answer(code)


@pytest.mark.asyncio
async def test_partial_execution_logs_precede_error_and_are_not_truncated(
    monkeypatch, tmp_path
):
    runner, _ = runner_for(
        monkeypatch,
        tmp_path,
        [
            (
                "<code>create_file('created.txt', 'data')\nprint('CREATED_OK')\nfor i in range(40):\n    print(i)\nread_file('missing.txt')</code>",
                TokenUsage(1, 1),
            ),
            ("<code>final_answer('partial failure')</code>", TokenUsage(1, 1)),
        ],
    )
    app = LocalCodeAgentApp(agent=runner)
    async with app.run_test() as pilot:
        app.query_one("#prompt", PromptInput).value = "create then read"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert (tmp_path / "created.txt").read_text() == "data"
        observations = [
            (i, text)
            for i, text in enumerate(app.transcript)
            if text.startswith("Tool > 结果")
        ]
        assert len(observations) == 1
        index, logs = observations[0]
        assert "CREATED_OK" in logs and "\n39" in logs
        assert app.transcript[index + 1].startswith("Tool > 错误")
        assert "missing.txt" in app.transcript[index + 1]
        assert "CREATED_OK" not in app.transcript[index + 1]


@pytest.mark.asyncio
async def test_error_does_not_repeat_observation_already_emitted_by_tool_output():
    from smolagents.agents import ToolOutput

    app = LocalCodeAgentApp()
    async with app.run_test():
        app.busy = True
        call = ToolCall(name="read_file", arguments={"file_path": "x"}, id="x")
        app._render_agent_event(call)
        app._render_agent_event(
            ToolOutput(
                id="x",
                output="read once",
                observation="read once",
                is_final_answer=False,
                tool_call=call,
            )
        )
        app._render_agent_event(
            ActionStep(
                step_number=1,
                timing=Timing(0, 1),
                observations="read once",
                error=ValueError("later error"),
            )
        )
        assert sum(text.startswith("Tool > 结果") for text in app.transcript) == 1
        assert app.transcript[-1] == "Tool > 错误\nlater error"


@pytest.mark.parametrize("absolute", [True, False])
def test_recursive_tree_preserves_same_name_files_under_different_parents(
    tmp_path, absolute
):
    paths = ["src/a.py", "tests/a.py"]
    items = [
        {"path": str(tmp_path / path) if absolute else path, "type": "file"}
        for path in paths
    ]
    tree = render_directory_tree({"items": items}, workspace_root=tmp_path)
    assert tmp_path.name in str(tree.label)
    branches = {str(child.label): child for child in tree.children}
    assert len(branches) == 2
    src = next(child for label, child in branches.items() if "src/" in label)
    tests = next(child for label, child in branches.items() if "tests/" in label)
    assert [str(child.label) for child in src.children] == ["🐍 a.py"]
    assert [str(child.label) for child in tests.children] == ["🐍 a.py"]


def test_recursive_tree_query_root_parent_reuse_links_and_limits(tmp_path):
    root = tmp_path / "src"
    items = [
        {"path": str(root / "pkg/a.py"), "type": "file"},
        {"path": str(root / "pkg"), "type": "directory"},
        {"path": str(root / "alias"), "type": "symlink"},
        {"path": str(root / "z.py"), "type": "file"},
    ]
    tree = render_directory_tree(
        {"items": items, "skipped": [str(root / "target")]},
        directory_name="src",
        workspace_root=tmp_path,
        max_items=3,
    )
    assert str(tree.label).startswith("📁 src/")
    packages = [child for child in tree.children if "pkg/" in str(child.label)]
    assert len(packages) == 1 and "a.py" in str(packages[0].children[0].label)
    assert any("alias [符号链接]" in str(child.label) for child in tree.children)
    assert any("省略其余 1 项" in str(child.label) for child in tree.children)
    assert any("概览忽略" in str(child.label) for child in tree.children)


def test_recursive_tree_without_workspace_uses_common_parent():
    tree = render_directory_tree(
        [
            {"path": "/repo/src/a.py", "type": "file"},
            {"path": "/repo/tests/a.py", "type": "file"},
        ]
    )
    assert str(tree.label).startswith("📁 repo/")
    assert len(tree.children) == 2
    assert all(len(child.children) == 1 for child in tree.children)


@pytest.mark.asyncio
async def test_user_interrupt_is_not_reported_as_failure():
    """Ctrl-C must not surface as a red failure card."""
    from unittest.mock import MagicMock

    from smolagents.utils import AgentError

    class InterruptingAgent:
        def run(self, prompt, event_callback=None):
            raise AgentError("Agent interrupted.", MagicMock())

    app = LocalCodeAgentApp(agent=InterruptingAgent())
    async with app.run_test() as pilot:
        app.query_one("#prompt", PromptInput).value = "task"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert any("已按用户请求中断本轮执行" in entry for entry in app.transcript)
        assert not any(entry.startswith("Error > ") for entry in app.transcript)
        assert app.busy is False


@pytest.mark.asyncio
async def test_ordinary_failure_still_reports_error_and_recovers():
    """Non-interrupt failures keep the visible error path and release the input."""

    class FailingAgent:
        def run(self, prompt, event_callback=None):
            raise RuntimeError("boom")

    app = LocalCodeAgentApp(agent=FailingAgent())
    async with app.run_test() as pilot:
        app.query_one("#prompt", PromptInput).value = "task"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert any(
            entry.startswith("Error > ") and "boom" in entry for entry in app.transcript
        )
        assert not any("已按用户请求中断" in entry for entry in app.transcript)
        assert app.busy is False


@pytest.mark.asyncio
async def test_cancel_uses_neutral_notice_and_releases_input():
    """Ctrl-C on a running turn must not render a red error card."""
    import time

    class SlowAgent:
        def run(self, prompt, event_callback=None):
            time.sleep(1.5)  # stand-in for an in-flight model request
            return "late"

    app = LocalCodeAgentApp(agent=SlowAgent())
    async with app.run_test() as pilot:
        app.query_one("#prompt", PromptInput).value = "task"
        await pilot.press("enter")
        await pilot.pause()
        app.action_cancel_or_quit()
        await pilot.pause()
        assert any("任务已被用户取消" in entry for entry in app.transcript)
        assert not any(entry.startswith("Error > ") for entry in app.transcript)
        assert app.busy is False
