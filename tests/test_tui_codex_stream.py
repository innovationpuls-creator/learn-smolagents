"""Comprehensive tests verifying the Codex-level lifecycle of streaming thoughts,
tool calls, execution results, error paths, and agent runner encapsulation."""

from __future__ import annotations

from typing import Any

import pytest
from smolagents.agents import (
    ActionOutput,
    ActionStep,
    AgentError,
    FinalAnswerStep,
    PlanningStep,
    Timing,
    TokenUsage,
    ToolCall,
    ToolOutput,
)
from smolagents.models import ChatMessageStreamDelta

from learn_smolagents.agent.runtime import SmolAgentRunner
from learn_smolagents.config import LLMConfig
from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.composer import PromptInput


class StreamingMockAgent:
    """Mock agent that simulates smolagents event streaming to test TUI sequencing."""

    def __init__(
        self, events_to_yield: list[Any], final_return: str | None = None
    ) -> None:
        self.events_to_yield = events_to_yield
        self.final_return = final_return

    def run(self, prompt: str, event_callback=None) -> str:
        if event_callback is not None:
            for ev in self.events_to_yield:
                event_callback(ev)
        if self.final_return is not None:
            return self.final_return
        for ev in reversed(self.events_to_yield):
            if isinstance(ev, FinalAnswerStep):
                return str(ev.output)
        return "Default answer"


@pytest.mark.asyncio
async def test_codex_stream_sequence_order() -> None:
    """Verify strictly ordered lifecycle:
    1. Thought -> 2. Tool Call -> 3. Tool Result -> 4. Final Thought -> 5. Agent Answer.
    Ensure pure final_answer code is NOT rendered as tool call or tool result."""
    events = [
        # Step 1: Think and call list_directory
        ChatMessageStreamDelta(content="Thought: I should check directory structure\n"),
        ChatMessageStreamDelta(
            content="<code>\nfiles = list_directory('.')\nprint(files)\n</code>"
        ),
        ToolCall(
            name="python_interpreter",
            arguments="files = list_directory('.')\nprint(files)",
            id="call_1",
        ),
        ActionOutput(output="['main.py', 'src']", is_final_answer=False),
        ActionStep(
            step_number=1,
            observations="Execution logs:\n['main.py', 'src']\nLast output from code snippet:\nNone",
            is_final_answer=False,
            timing=Timing(start_time=0.0, end_time=0.15),
            token_usage=TokenUsage(input_tokens=50, output_tokens=30),
        ),
        # Step 2: Formulate final answer
        ChatMessageStreamDelta(content="Thought: Found files, ready to report.\n"),
        ChatMessageStreamDelta(
            content="<code>\nfinal_answer('Project has main.py and src')\n</code>"
        ),
        ToolCall(
            name="python_interpreter",
            arguments="final_answer('Project has main.py and src')",
            id="call_2",
        ),
        ActionOutput(output="Project has main.py and src", is_final_answer=True),
        ActionStep(
            step_number=2,
            observations="Execution logs:\nLast output from code snippet:\nProject has main.py and src",
            is_final_answer=True,
            timing=Timing(start_time=0.15, end_time=0.25),
            token_usage=TokenUsage(input_tokens=40, output_tokens=20),
        ),
        FinalAnswerStep(output="Project has main.py and src"),
    ]

    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "List project files"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        transcript = app.transcript

        # 1. User message first
        assert transcript[0] == "You > List project files"

        # 2. First thought flushed BEFORE tool call
        assert "Trace > I should check directory structure" in transcript
        thought_idx = transcript.index("Trace > I should check directory structure")

        # 3. Tool call rendered with identified tool name
        tool_call_entry = next(
            e for e in transcript if "Tool > 调用 [python_interpreter]" in e
        )
        tool_call_idx = transcript.index(tool_call_entry)
        assert thought_idx < tool_call_idx

        # 4. Tool observation rendered with cleaned output (no noisy boilerplate)
        tool_res_entry = next(e for e in transcript if "Tool > 结果" in e)
        tool_res_idx = transcript.index(tool_res_entry)
        assert tool_call_idx < tool_res_idx
        assert "['main.py', 'src']" in tool_res_entry
        assert "Execution logs:" not in tool_res_entry

        # 5. Second thought flushed
        assert "Trace > Found files, ready to report." in transcript
        second_thought_idx = transcript.index("Trace > Found files, ready to report.")
        assert tool_res_idx < second_thought_idx

        # 6. Crucial check: pure final_answer MUST NOT produce tool call or fake tool observation
        assert not any("Tool > 调用 [final_answer]" in e for e in transcript)
        assert not any(
            "Tool > 结果\nProject has main.py and src" in e for e in transcript
        )

        # 7. Agent response is at the end
        agent_idx = transcript.index("Agent > Project has main.py and src")
        assert second_thought_idx < agent_idx


@pytest.mark.asyncio
async def test_tool_execution_error_handling() -> None:
    """Verify tool execution errors are captured cleanly in timeline without breaking TUI."""
    events = [
        ChatMessageStreamDelta(content="Thought: attempting to delete invalid file\n"),
        ToolCall(
            name="python_interpreter",
            arguments="delete_file('/nonexistent/file.txt')",
            id="call_err",
        ),
        ActionStep(
            step_number=1,
            observations="",
            error=FileNotFoundError("文件不存在：/nonexistent/file.txt"),
            is_final_answer=False,
            timing=Timing(start_time=0.0, end_time=0.1),
        ),
        ChatMessageStreamDelta(content="Thought: file missing, aborting\n"),
        FinalAnswerStep(output="无法删除不存在的文件。"),
    ]

    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Delete bad file"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        # Check that error is recorded with Tool > 错误
        error_entries = [e for e in app.transcript if "Tool > 错误" in e]
        assert len(error_entries) == 1
        assert "文件不存在" in error_entries[0]

        # Check final answer completes
        assert "Agent > 无法删除不存在的文件。" in app.transcript


@pytest.mark.asyncio
async def test_planning_step_rendering() -> None:
    """Verify PlanningStep is rendered cleanly into the timeline."""
    plan_text = "1. 读取配置文件\n2. 校验配置内容\n3. 输出总结"
    events = [
        PlanningStep(
            model_input_messages=[],
            model_output_message=None,  # type: ignore[arg-type]
            plan=plan_text,
            timing=Timing(start_time=0.0, end_time=0.4),
        ),
        ChatMessageStreamDelta(content="Thought: Starting step 1\n"),
        FinalAnswerStep(output="计划执行完毕"),
    ]

    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Execute plan"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert any("Trace > 规划" in e and "读取配置文件" in e for e in app.transcript)
        assert "Agent > 计划执行完毕" in app.transcript


@pytest.mark.asyncio
async def test_direct_tool_calling_agent_event() -> None:
    """Verify non-python_interpreter ToolCalls (ToolCallingAgent) format correctly."""
    events = [
        ChatMessageStreamDelta(content="Thought: Calling read_file tool directly\n"),
        ToolCall(
            name="read_file",
            arguments="{'file_path': 'pyproject.toml'}",
            id="call_read",
        ),
        ActionStep(
            step_number=1,
            observations="[project]\nname = 'learn-smolagents'",
            is_final_answer=False,
            timing=Timing(start_time=0.0, end_time=0.05),
        ),
        FinalAnswerStep(output="Read successfully"),
    ]

    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Read pyproject"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert any("Tool > 调用 [read_file]" in e for e in app.transcript)
        assert any(
            "Tool > 结果" in e and "learn-smolagents" in e for e in app.transcript
        )
        assert "Agent > Read successfully" in app.transcript


def test_smolagent_runner_methods(monkeypatch) -> None:
    """Verify SmolAgentRunner methods: run, interrupt, reset_memory, and last_result."""

    class FakeMemory:
        def __init__(self):
            self.steps = []

        def reset(self):
            self.steps.clear()

        def get_succinct_steps(self):
            return [{"type": "mock"}]

    class FakeAgent:
        def __init__(self, **kwargs):
            self.memory = FakeMemory()
            self.interrupt_switch = False

        def run(self, prompt, **kwargs):
            if kwargs.get("stream"):
                return [FinalAnswerStep(output=f"Streamed: {prompt}")]
            return f"Direct: {prompt}"

    from learn_smolagents.agent import runtime as agent_module

    monkeypatch.setattr(agent_module, "OpenAIModel", lambda **kw: None)
    monkeypatch.setattr(agent_module, "CodeAgent", FakeAgent)

    runner = SmolAgentRunner(config=LLMConfig("test-model", "https://api.test", "key"))

    # 1. Direct run
    assert runner.run("hello") == "Direct: hello"

    # 2. Stream run with callback
    collected = []
    out = runner.run("stream me", event_callback=collected.append)
    assert out == "Streamed: stream me"
    assert len(collected) == 1
    assert isinstance(collected[0], FinalAnswerStep)

    # 3. Interrupt
    assert not runner._agent.interrupt_switch
    runner.interrupt()
    assert runner._agent.interrupt_switch

    # 4. Memory reset and steps
    assert runner.memory_steps() == [{"type": "mock"}]
    runner.reset_memory()
    assert runner.memory_steps() == [{"type": "mock"}]


@pytest.mark.asyncio
async def test_multi_step_tool_call_pairing() -> None:
    """Verify that multiple tool calls in multi-step agents maintain exact 1:1 order:
    Thought 1 -> ToolCall 1 -> Obs 1 -> Thought 2 -> ToolCall 2 -> Obs 2 -> Answer."""
    events = [
        # Step 1: list_directory
        ChatMessageStreamDelta(content="思考：检查当前目录文件列表\n"),
        ToolCall(
            name="python_interpreter",
            arguments="list_directory('.')",
            id="call_1",
        ),
        ActionStep(
            step_number=1,
            observations="Execution logs:\n['a.py', 'b.py']\nLast output from code snippet:\nNone",
            is_final_answer=False,
            timing=Timing(0.0, 0.1),
        ),
        # Step 2: read_file
        ChatMessageStreamDelta(content="思考：读取 a.py 文件内容\n"),
        ToolCall(
            name="python_interpreter",
            arguments="read_file('a.py')",
            id="call_2",
        ),
        ActionStep(
            step_number=2,
            observations="Execution logs:\nprint('hello world')\nLast output from code snippet:\nNone",
            is_final_answer=False,
            timing=Timing(0.1, 0.2),
        ),
        # Step 3: edit_file
        ChatMessageStreamDelta(content="思考：更新 a.py 文件内容\n"),
        ToolCall(
            name="python_interpreter",
            arguments="edit_file('a.py', 'hello', 'hi')",
            id="call_3",
        ),
        ActionStep(
            step_number=3,
            observations="Execution logs:\n{'bytes_written': 15}\nLast output from code snippet:\nNone",
            is_final_answer=False,
            timing=Timing(0.2, 0.3),
        ),
        # Step 4: Final answer
        ChatMessageStreamDelta(content="Thought: All steps complete.\n"),
        FinalAnswerStep(output="a.py 成功修改为 hi"),
    ]

    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Modify a.py"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        transcript = app.transcript

        # Check chronological indices
        idx_t1 = transcript.index("Trace > 检查当前目录文件列表")
        idx_c1 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 调用 [python_interpreter]" in e
        )
        idx_o1 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 结果" in e and "['a.py', 'b.py']" in e
        )

        idx_t2 = transcript.index("Trace > 读取 a.py 文件内容")
        idx_c2 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 调用 [python_interpreter]" in e and "read_file(" in e
        )
        idx_o2 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 结果" in e and "print('hello world')" in e
        )

        idx_t3 = transcript.index("Trace > 更新 a.py 文件内容")
        idx_c3 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 调用 [python_interpreter]" in e and "edit_file(" in e
        )
        idx_o3 = next(
            i
            for i, e in enumerate(transcript)
            if "Tool > 结果" in e and "bytes_written" in e
        )

        idx_ans = transcript.index("Agent > a.py 成功修改为 hi")

        assert (
            idx_t1
            < idx_c1
            < idx_o1
            < idx_t2
            < idx_c2
            < idx_o2
            < idx_t3
            < idx_c3
            < idx_o3
            < idx_ans
        )


def test_observation_truncation_for_large_outputs() -> None:
    """Verify that very large outputs from tools are bounded without flooding the terminal."""
    large_output = (
        "Execution logs:\n"
        + "\n".join(f"line {i}" for i in range(100))
        + "\nLast output from code snippet:\nNone"
    )
    cleaned = LocalCodeAgentApp._clean_action_step_observation(
        large_output, max_lines=20
    )
    lines = cleaned.splitlines()
    assert len(lines) == 21  # 20 lines + truncation notice
    assert "省略其余 80 行输出" in lines[-1]


def test_thought_code_splitting_variants() -> None:
    """Verify robust splitting across different code block tags and thought prefixes."""
    # Variant 1: Chinese prefix with <code>
    raw1 = "思考：需要查询文档。\n<code>\nread_file('doc.md')\n</code>"
    thought1, code1, has_code1 = LocalCodeAgentApp._split_thought_and_code(raw1)
    assert thought1 == "需要查询文档。"
    assert "read_file('doc.md')" in code1
    assert has_code1

    # Variant 2: ```python markdown block
    raw2 = "Thoughts: Let's run a check.\n```python\nfiles = list_directory()\n```"
    thought2, code2, has_code2 = LocalCodeAgentApp._split_thought_and_code(raw2)
    assert thought2 == "Let's run a check."
    assert "files = list_directory()" in code2
    assert has_code2

    # Variant 3: No code, pure thought
    raw3 = "Thought: Just pondering the question..."
    thought3, code3, has_code3 = LocalCodeAgentApp._split_thought_and_code(raw3)
    assert thought3 == "Just pondering the question..."
    assert code3 == ""
    assert not has_code3


@pytest.mark.asyncio
async def test_final_answer_with_computation_preserves_execution() -> None:
    """Keep code that computes the answer visible rather than assuming it is side-effect free."""
    events = [
        ChatMessageStreamDelta(content="Thought: Organizing the response.\n"),
        ToolCall(
            name="python_interpreter",
            arguments="# Final calculation\nmsg = 'Processed ' + str(42) + ' items'\nfinal_answer(msg)",
            id="call_fa",
        ),
        ActionOutput(output="Processed 42 items", is_final_answer=True),
        ActionStep(
            step_number=1,
            observations="",
            is_final_answer=True,
            timing=Timing(0.0, 0.1),
        ),
        FinalAnswerStep(output="Processed 42 items"),
    ]
    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Process items"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        # Keep the computation; there is no observation in this synthetic event.
        assert any("Tool > 调用 [python_interpreter]" in e for e in app.transcript)
        assert not any("Tool > 结果" in e for e in app.transcript)
        assert "Agent > Processed 42 items" in app.transcript


@pytest.mark.asyncio
async def test_tool_calling_agent_final_answer_tool_call() -> None:
    """Verify ToolCallingAgent calling final_answer tool directly does NOT produce tool call card."""
    tc = ToolCall(
        name="final_answer",
        arguments="{'answer': 'Everything looks good'}",
        id="call_final_tool",
    )
    events = [
        ChatMessageStreamDelta(content="Thought: Sending final answer.\n"),
        tc,
        ToolOutput(
            id="call_final_tool",
            output="Everything looks good",
            is_final_answer=True,
            observation="Everything looks good",
            tool_call=tc,
        ),
        ActionOutput(output="Everything looks good", is_final_answer=True),
        ActionStep(
            step_number=1,
            observations="Everything looks good",
            is_final_answer=True,
            timing=Timing(0.0, 0.1),
        ),
        FinalAnswerStep(output="Everything looks good"),
    ]
    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Check system"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert not any("Tool > 调用 [final_answer]" in e for e in app.transcript)
        assert not any("Tool > 结果" in e for e in app.transcript)
        assert "Agent > Everything looks good" in app.transcript


@pytest.mark.asyncio
async def test_planning_step_does_not_duplicate_thought_card() -> None:
    """Verify streaming deltas before PlanningStep do NOT leave a duplicate thought card."""
    events = [
        ChatMessageStreamDelta(content="Plan:\n1. Check config\n2. Run audit"),
        PlanningStep(
            model_input_messages=[],
            model_output_message=None,  # type: ignore[arg-type]
            plan="1. Check config\n2. Run audit",
            timing=Timing(0.0, 0.2),
        ),
        FinalAnswerStep(output="Audit ready"),
    ]
    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Plan audit"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        plan_entries = [e for e in app.transcript if "Trace > 规划" in e]
        thought_entries = [
            e for e in app.transcript if "Trace >" in e and "Trace > 规划" not in e
        ]

        assert len(plan_entries) == 1
        assert len(thought_entries) == 0  # No duplicate thought card!


@pytest.mark.asyncio
async def test_tool_call_and_final_answer_in_same_step_preserves_observation() -> None:
    """Verify when code calls a tool AND final_answer in the same step, observation is NOT swallowed."""
    events = [
        ChatMessageStreamDelta(content="Thought: Listing and finishing.\n"),
        ToolCall(
            name="python_interpreter",
            arguments="files = list_directory('.')\nfinal_answer(files)",
            id="call_both",
        ),
        ActionOutput(output="['x.txt']", is_final_answer=True),
        ActionStep(
            step_number=1,
            observations="Execution logs:\n['x.txt']\nLast output from code snippet:\nNone",
            is_final_answer=True,
            timing=Timing(0.0, 0.1),
        ),
        FinalAnswerStep(output="['x.txt']"),
    ]
    agent = StreamingMockAgent(events)
    app = LocalCodeAgentApp(agent=agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "List and finish"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        # Tool call MUST be rendered
        assert any("Tool > 调用 [python_interpreter]" in e for e in app.transcript)
        # Tool result MUST NOT be swallowed
        assert any("Tool > 结果" in e and "['x.txt']" in e for e in app.transcript)


def test_multi_tool_code_keeps_interpreter_identity() -> None:
    """Verify earliest called tool is identified rather than arbitrary tuple search order."""
    code = "res = list_directory('.')\ndata = read_file('test.txt')"
    tool_call = ToolCall(name="python_interpreter", arguments=code, id="c1")
    assert LocalCodeAgentApp._detect_tool_name(tool_call) == "python_interpreter"


@pytest.mark.asyncio
async def test_user_interruption_does_not_produce_tool_error_card() -> None:
    """Verify ActionStep with interrupted error does not print a bogus Tool > 错误 card."""
    from unittest.mock import MagicMock

    events = [
        ChatMessageStreamDelta(content="Thought: Thinking..."),
        ActionStep(
            step_number=1,
            observations="",
            error=AgentError("Agent interrupted.", logger=MagicMock()),
            is_final_answer=False,
            timing=Timing(0.0, 0.1),
        ),
    ]
    agent = StreamingMockAgent(events, final_return="中断")
    app = LocalCodeAgentApp(agent=agent)
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "Interrupt me"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        assert not any("Tool > 错误" in e for e in app.transcript)
