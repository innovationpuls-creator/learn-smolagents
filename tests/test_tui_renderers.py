"""Unit tests for Codex-level structured renderers in Local CodeAgent TUI."""

from __future__ import annotations

import pytest
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from textual.widgets import RichLog

from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.composer import PromptInput
from learn_smolagents.ui.renderers import (
    extract_tool_arguments,
    get_file_icon_and_style,
    render_data_table,
    render_directory_tree,
    render_error_card,
    render_file_content,
    render_file_diff,
    render_plan_card,
    render_search_results,
    render_thought_card,
    render_tool_call_card,
    render_tool_result_card,
    try_parse_structured,
)


def test_get_file_icon_and_style() -> None:
    assert get_file_icon_and_style("main.py")[0] == "🐍"
    assert get_file_icon_and_style("index.html")[0] == "🌐"
    assert get_file_icon_and_style("styles.css")[0] == "🎨"
    assert get_file_icon_and_style("package.json")[0] == "⚙ "
    assert get_file_icon_and_style("config.toml")[0] == "⚙ "
    assert get_file_icon_and_style("README.md")[0] == "📝"
    assert get_file_icon_and_style("deploy.sh")[0] == "⚡"
    assert get_file_icon_and_style("logo.png")[0] == "🖼 "
    assert get_file_icon_and_style("archive.zip")[0] == "📦"
    assert get_file_icon_and_style("db.sql")[0] == "💾"
    assert get_file_icon_and_style(".gitignore")[0] == "📄"
    assert get_file_icon_and_style("unknown.xyz")[0] == "📄"


def test_try_parse_structured_dict_repr() -> None:
    raw = "{'items': [{'path': '/test/a.py', 'type': 'file'}]}"
    parsed, extra = try_parse_structured(raw)
    assert isinstance(parsed, dict)
    assert "items" in parsed
    assert extra == ""


def test_try_parse_structured_json() -> None:
    raw = '{"results": [{"file_path": "foo.py", "line_number": 1, "text": "bar"}]}'
    parsed, extra = try_parse_structured(raw)
    assert isinstance(parsed, dict)
    assert "results" in parsed
    assert extra == ""


def test_try_parse_structured_embedded_in_logs() -> None:
    raw = "Execution logs:\nScanning directory...\n{'items': [{'path': 'x', 'type': 'file'}]}\n-> None"
    parsed, extra = try_parse_structured(raw)
    assert isinstance(parsed, dict)
    assert "items" in parsed
    assert "Scanning directory..." in extra


def test_try_parse_structured_plain_text() -> None:
    raw = "Just a plain message from script"
    parsed, extra = try_parse_structured(raw)
    assert parsed is None
    assert extra == raw


def test_extract_tool_arguments_python_ast() -> None:
    code = "contents = list_directory(directory_path='src')\nprint(contents)"
    args = extract_tool_arguments("list_directory", code)
    assert args == {"directory_path": "src"}

    code2 = "edit_file('test.py', old_content='a', new_content='b')"
    args2 = extract_tool_arguments("edit_file", code2)
    assert args2 == {"file_path": "test.py", "old_content": "a", "new_content": "b"}

    code3 = "read_file(file_path='pyproject.toml')"
    args3 = extract_tool_arguments("read_file", code3)
    assert args3 == {"file_path": "pyproject.toml"}


def test_extract_tool_arguments_json() -> None:
    raw_json = '{"directory_path": ".", "recursive": false}'
    args = extract_tool_arguments("list_directory", raw_json)
    assert args.get("directory_path") == "."


def test_render_directory_tree_empty() -> None:
    tree = render_directory_tree([], directory_name="test")
    assert isinstance(tree, Tree)
    label_str = str(tree.label)
    assert "0 目录 · 0 文件" in label_str


def test_render_directory_tree_dict_items() -> None:
    items = [
        {"path": "/opt/test/src", "type": "directory"},
        {"path": "/opt/test/target", "type": "directory"},
        {"path": "/opt/test/main.py", "type": "file"},
        {"path": "/opt/test/pom.xml", "type": "file"},
    ]
    tree = render_directory_tree({"items": items}, directory_name="test")
    assert isinstance(tree, Tree)
    label_str = str(tree.label)
    assert "2 目录 · 2 文件" in label_str

    child_labels = [str(c.label) for c in tree.children]
    # Directories appear first
    assert any("src/" in cl for cl in child_labels)
    assert any("target/" in cl for cl in child_labels)
    assert any("main.py" in cl for cl in child_labels)
    assert any("pom.xml" in cl for cl in child_labels)


def test_render_directory_tree_truncation() -> None:
    items = [{"path": f"/opt/test/file_{i}.py", "type": "file"} for i in range(50)]
    tree = render_directory_tree(items, directory_name="test", max_items=20)
    assert len(tree.children) == 21  # 20 items + 1 truncation notice
    assert any("省略其余" in str(c.label) for c in tree.children)


def test_render_search_results() -> None:
    results = [
        {"file_path": "/app/src/main.py", "line_number": 10, "text": "def execute():"},
        {"file_path": "/app/src/main.py", "line_number": 25, "text": "    execute()"},
        {"file_path": "/app/tests/test.py", "line_number": 5, "text": "execute()"},
    ]
    tree = render_search_results(results, search_string="execute")
    assert isinstance(tree, Tree)
    label_str = str(tree.label)
    assert "3 处匹配 · 2 个文件" in label_str
    assert len(tree.children) == 2


def test_render_search_results_empty() -> None:
    res = render_search_results([])
    assert isinstance(res, Text)
    assert "未找到匹配" in str(res)


def test_render_file_content() -> None:
    code = "def hello():\n    return 42\n"
    rendered = render_file_content(code, file_path="main.py")
    assert isinstance(rendered, Syntax)
    assert rendered.lexer.name.lower() in ("python", "python 3")


def test_render_file_content_truncation() -> None:
    code = "\n".join(f"line_{i} = {i}" for i in range(100))
    rendered = render_file_content(code, file_path="big.py", max_lines=20)
    # Returns a Group containing Syntax and truncation notice
    from rich.console import Group

    assert isinstance(rendered, Group)


def test_render_file_diff() -> None:
    old = "def foo():\n    return 1\n"
    new = "def foo():\n    return 2\n"
    syntax, summary = render_file_diff(old, new, file_path="foo.py")
    assert isinstance(syntax, Syntax)
    assert "+1 / -1 行" in summary


def test_render_data_table() -> None:
    data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    table = render_data_table(data)
    assert isinstance(table, Table)
    assert len(table.columns) == 2
    assert len(table.rows) == 2

    # Non-tabular data returns None
    assert render_data_table("not a table") is None


def test_render_tool_call_card_python() -> None:
    code = "contents = list_directory('.')\nprint(contents)"
    panel = render_tool_call_card("list_directory", code)
    assert isinstance(panel, Panel)
    assert "调用工具" in str(panel.title)
    assert "list_directory" in str(panel.title)
    assert isinstance(panel.renderable, Syntax)


def test_render_tool_call_card_json() -> None:
    args = '{"path": "foo.txt"}'
    panel = render_tool_call_card("read_file", args)
    assert isinstance(panel, Panel)
    assert "read_file" in str(panel.title)
    assert isinstance(panel.renderable, Syntax)


def test_render_tool_result_card_list_directory() -> None:
    obs = "{'items': [{'path': '/a/b/c.py', 'type': 'file'}, {'path': '/a/b/sub', 'type': 'directory'}]}"
    panel = render_tool_result_card(
        obs,
        duration=0.5,
        is_error=False,
        tool_context={
            "tool_name": "list_directory",
            "extracted_args": {"directory_path": "."},
        },
    )
    assert isinstance(panel, Panel)
    assert "观察结果" in str(panel.title)
    assert "0.5s" in str(panel.title)
    # The renderable should be the Tree
    assert isinstance(panel.renderable, Tree)


def test_render_tool_result_card_edit_file() -> None:
    obs = "{'path': '/workspace/test.py', 'bytes_written': 42}"
    tool_ctx = {
        "tool_name": "edit_file",
        "extracted_args": {
            "file_path": "test.py",
            "old_content": "print('hello')",
            "new_content": "print('world')",
        },
    }
    panel = render_tool_result_card(
        obs, duration=0.1, is_error=False, tool_context=tool_ctx
    )
    assert isinstance(panel, Panel)
    assert "test.py" in str(panel.subtitle)
    assert isinstance(panel.renderable, Syntax)


def test_render_tool_result_card_error() -> None:
    obs = "FileNotFoundError: 文件不存在：/missing.txt"
    panel = render_tool_result_card(obs, duration=0.2, is_error=True)
    assert isinstance(panel, Panel)
    assert "执行异常" in str(panel.title)
    assert "0.2s" in str(panel.title)


def test_render_thought_and_plan_cards() -> None:
    thought_p = render_thought_card("我需要先查阅目录结构", duration=1.2)
    assert isinstance(thought_p, Panel)
    assert "思考过程" in str(thought_p.title)
    assert "1.2s" in str(thought_p.title)

    plan_p = render_plan_card("1. 读取配置\n2. 编辑文件", duration=0.4)
    assert isinstance(plan_p, Panel)
    assert "任务规划" in str(plan_p.title)
    assert "0.4s" in str(plan_p.title)


def test_render_error_card() -> None:
    err_p = render_error_card("Something went wrong", duration=0.1)
    assert isinstance(err_p, Panel)
    assert "错误" in str(err_p.title)


@pytest.mark.asyncio
async def test_tui_timeline_receives_structured_panels() -> None:
    """Verify that when agent events are emitted, the ConversationView log actually receives Panel instances."""
    from smolagents.agents import ActionStep, Timing, ToolCall

    class MockAgent:
        def run(self, prompt: str, event_callback=None) -> str:
            if event_callback is not None:
                # 1. Tool call
                event_callback(
                    ToolCall(
                        name="python_interpreter",
                        arguments="contents = list_directory('.')\nprint(contents)",
                        id="c1",
                    )
                )
                # 2. Tool observation
                obs_data = "{'items': [{'path': '/workspace/main.py', 'type': 'file'}, {'path': '/workspace/src', 'type': 'directory'}]}"
                event_callback(
                    ActionStep(
                        step_number=1,
                        observations=f"Execution logs:\n{obs_data}\nLast output from code snippet:\nNone",
                        is_final_answer=False,
                        timing=Timing(start_time=0.0, end_time=0.3),
                    )
                )
            return "目录列出完成"

    app = LocalCodeAgentApp(agent=MockAgent())
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptInput)
        prompt.value = "List workspace"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

        # Check transcript backwards-compatibility
        assert any("Tool > 调用 [python_interpreter]" in e for e in app.transcript)
        assert any("Tool > 结果" in e and "items" in e for e in app.transcript)
        assert "Agent > 目录列出完成" in app.transcript

        # Check conversation RichLog contents
        log = app.query_one("#conversation", RichLog)
        assert len(log.lines) > 0

        # Verify that the log contains rendered panels with box borders and tree symbols
        all_text = "\n".join(line.text for line in log.lines)
        assert "╭─" in all_text  # Box top border
        assert "╰─" in all_text  # Box bottom border
        assert "执行 Python [python_interpreter]" in all_text
        assert "观察结果" in all_text
        assert "📁" in all_text
        assert "src/" in all_text
        assert "main.py" in all_text


def test_read_file_with_json_items_not_hijacked_into_tree() -> None:
    """Ensure read_file reading a json file containing an 'items' key is rendered as file content, NOT a directory tree."""
    json_content = '{"items": ["apple", "banana"]}'
    panel = render_tool_result_card(
        json_content,
        tool_context={
            "tool_name": "read_file",
            "extracted_args": {"file_path": "fruits.json"},
        },
    )
    assert isinstance(panel, Panel)
    assert not isinstance(panel.renderable, Tree)
    assert "fruits.json" in str(panel.subtitle)
    assert isinstance(panel.renderable, Syntax)
    assert panel.renderable.lexer.name.lower() == "json"


def test_render_tool_call_card_compact_equality_syntax() -> None:
    """Ensure tool calls like list_directory(directory_path='.') are syntax highlighted as Python."""
    code = 'list_directory(directory_path=".")'
    panel = render_tool_call_card("list_directory", code)
    assert isinstance(panel, Panel)
    assert isinstance(panel.renderable, Syntax)
    assert panel.renderable.lexer.name.lower() in ("python", "python 3")


def test_try_parse_structured_list_of_dicts_in_logs() -> None:
    """Ensure list of dicts embedded in logs is parsed as list and rendered as Table."""
    raw = "[INFO] Scanning: [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]"
    parsed, extra = try_parse_structured(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert "Scanning:" in extra
    panel = render_tool_result_card(raw)
    assert isinstance(panel, Panel)
    from rich.console import Group

    assert isinstance(panel.renderable, Group)
    assert any(isinstance(elem, Table) for elem in panel.renderable.renderables)


def test_render_search_results_non_dict_safe() -> None:
    """Ensure non-dict elements in results list do not raise AttributeError."""
    panel = render_tool_result_card('{"results": [100, 200]}')
    assert isinstance(panel, Panel)
    assert isinstance(panel.renderable, Syntax)


def test_render_tool_result_card_non_dir_items_as_json() -> None:
    """Ensure non-directory items like {'items': [1, 2, 3]} render as JSON, not empty directory tree."""
    panel = render_tool_result_card('{"items": [1, 2, 3]}')
    assert isinstance(panel, Panel)
    assert not isinstance(panel.renderable, Tree)
    assert isinstance(panel.renderable, Syntax)


def test_directory_tree_known_files() -> None:
    """Ensure extensionless files (Dockerfile, Makefile, LICENSE) are treated as files, not directories."""
    tree = render_directory_tree(
        ["Dockerfile", "Makefile", "LICENSE", "src/"], directory_name="repo"
    )
    child_labels = [str(c.label) for c in tree.children]
    # src should be a directory with folder icon
    assert any("📁 " in cl and "src/" in cl for cl in child_labels)
    # Dockerfile, Makefile, LICENSE should be files
    assert any("🐳 " in cl and "Dockerfile" in cl for cl in child_labels)
    assert any("🛠 " in cl and "Makefile" in cl for cl in child_labels)
    assert any("⚖ " in cl and "LICENSE" in cl for cl in child_labels)


def test_extract_tool_arguments_with_variables() -> None:
    """Ensure variables assigned before tool calls are resolved in extracted_args."""
    code = """f = "test.py"
old = "foo"
new = "bar"
edit_file(f, old, new_content=new)"""
    args = extract_tool_arguments("edit_file", code)
    assert args.get("file_path") == "test.py"
    assert args.get("old_content") == "foo"
    assert args.get("new_content") == "bar"


def test_case_insensitive_search_highlighting() -> None:
    """Ensure case-insensitive query matches are highlighted in search results."""
    results = [
        {"file_path": "readme.md", "line_number": 1, "text": "Welcome to Order System"}
    ]
    tree = render_search_results(results, search_string="order")
    assert isinstance(tree, Tree)
    # File branch has children
    file_branch = tree.children[0]
    line_node = file_branch.children[0]
    # Check that 'Order' in the rendered text has bold style
    rendered_text = line_node.label
    assert isinstance(rendered_text, Text)
    # Find span for 'Order'
    spans = [s for s in rendered_text.spans if "bold" in str(s.style)]
    assert len(spans) > 0


def test_observation_structured_not_truncated_by_prior_logs() -> None:
    """Ensure structured data is not truncated if preceded by >20 lines of logs."""
    logs = "\n".join(f"log line {i}" for i in range(35))
    payload = '{"items": [{"path": "/opt/app/main.py", "type": "file"}]}'
    raw = f"Execution logs:\n{logs}\nLast output from code snippet:\n{payload}"
    cleaned = LocalCodeAgentApp._clean_action_step_observation(raw, max_lines=20)
    assert "main.py" in cleaned
    parsed, _ = try_parse_structured(cleaned)
    assert isinstance(parsed, dict)
    assert "items" in parsed


def test_read_file_with_logs_not_duplicated() -> None:
    """Ensure read_file with execution logs does not duplicate the file content in the panel."""
    obs = "Reading file...\n\n-> def hello():\n    return 1"
    panel = render_tool_result_card(
        obs,
        duration=0.1,
        tool_context={
            "tool_name": "read_file",
            "extracted_args": {"file_path": "hello.py"},
        },
    )
    assert isinstance(panel, Panel)
    from rich.console import Group

    assert isinstance(panel.renderable, Group)
    # The first element is the logs Text, the second is Syntax
    assert isinstance(panel.renderable.renderables[0], Text)
    assert "Reading file..." in str(panel.renderable.renderables[0])
    assert isinstance(panel.renderable.renderables[1], Syntax)
    assert "hello.py · 2 行" in str(panel.subtitle)
