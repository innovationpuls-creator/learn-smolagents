"""Unit tests covering P0, P1, and P2 optimizations.

Native prompt integration is tested in test_runtime_regressions.py.
P1: Filesystem delete_directory recursive support and list_directory traversal.
P2: Native tool identity and visible parsing recovery in TUI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from smolagents.agents import ActionStep, Timing, ToolCall
from smolagents.utils import AgentParsingError

from learn_smolagents.permissions import FileAccess
from learn_smolagents.tools.filesystem import build_file_tools
from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.workspace import Workspace
from learn_smolagents.workspace.store import WorkspaceStore


def test_p1_delete_directory_non_empty_refusal_when_not_recursive(
    tmp_path: Path,
) -> None:
    """P1: Verify delete_directory refuses non-empty directory when recursive=False."""
    workspace = Workspace(tmp_path)
    access = FileAccess(workspace, full_access=True)
    tools = {t.name: t for t in build_file_tools(access)}

    sub_dir = tmp_path / "my_project"
    sub_dir.mkdir()
    (sub_dir / "file.txt").write_text("hello")

    with pytest.raises(ValueError, match="目录非空，不能删除"):
        tools["delete_directory"](str(sub_dir), recursive=False)

    assert sub_dir.exists()
    assert (sub_dir / "file.txt").exists()


def test_p1_delete_directory_recursive_success(tmp_path: Path) -> None:
    """P1: Verify delete_directory successfully removes non-empty directory tree when recursive=True."""
    workspace = Workspace(tmp_path)
    access = FileAccess(workspace, full_access=True)
    tools = {t.name: t for t in build_file_tools(access)}

    sub_dir = tmp_path / "my_project"
    nested_dir = sub_dir / "nested" / "deep"
    nested_dir.mkdir(parents=True)
    (nested_dir / "deep_file.txt").write_text("deep content")
    (sub_dir / "root_file.txt").write_text("root content")

    res = tools["delete_directory"]("my_project", recursive=True)
    assert res.get("deleted") is True
    assert res.get("recursive") is True
    assert not sub_dir.exists()


def test_p1_delete_directory_recursive_on_workspace_root(tmp_path: Path) -> None:
    """P1: Verify delete_directory on workspace root clears its contents but preserves root itself."""
    workspace = Workspace(tmp_path)
    access = FileAccess(workspace, full_access=True)
    tools = {t.name: t for t in build_file_tools(access)}

    # Create several files and directories inside workspace root
    (tmp_path / "README.md").write_text("# Project")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "main.py").write_text("print('hi')")

    res = tools["delete_directory"](".", recursive=True)
    assert res.get("deleted") is True
    assert res.get("cleared_workspace_root") is True
    assert res.get("items_deleted") == 2
    # Workspace root itself MUST still exist!
    assert tmp_path.exists()
    assert tmp_path.is_dir()
    # But all children must be gone
    assert list(tmp_path.iterdir()) == []


def test_p1_list_directory_non_recursive_and_recursive(tmp_path: Path) -> None:
    """P1: Verify list_directory non-recursive vs recursive traversal and ignored dirs."""
    workspace = Workspace(tmp_path)
    access = FileAccess(workspace, full_access=True)
    tools = {t.name: t for t in build_file_tools(access)}

    # Create directory tree
    (tmp_path / "file1.txt").write_text("1")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("app")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config")

    # Non-recursive
    res_flat = tools["list_directory"](".", recursive=False)
    paths_flat = [p["path"] for p in res_flat["items"]]
    assert str(tmp_path / "file1.txt") in paths_flat
    assert str(src) in paths_flat
    # Non-recursive does not dive into src
    assert str(src / "app.py") not in paths_flat

    # Recursive
    res_rec = tools["list_directory"](".", recursive=True, max_depth=2)
    paths_rec = [p["path"] for p in res_rec["items"]]
    assert str(tmp_path / "file1.txt") in paths_rec
    assert str(src / "app.py") in paths_rec
    # .git directory should be filtered out
    assert not any(".git" in p for p in paths_rec)


def test_p2_tool_event_identity_is_preserved() -> None:
    call = ToolCall(
        name="python_interpreter", arguments="custom_analyzer(data='abc')", id="x"
    )
    assert (
        LocalCodeAgentApp._detect_tool_name(call, {"custom_analyzer"})
        == "python_interpreter"
    )


@pytest.mark.asyncio
async def test_p2_action_step_records_parsing_recovery(tmp_path: Path) -> None:
    """P2: Verify ActionStep with regex pattern / code parsing error does NOT create a red Tool > 错误 card."""
    store = WorkspaceStore(tmp_path / "config.json", tmp_path)
    app = LocalCodeAgentApp(workspace_store=store)
    async with app.run_test(size=(80, 24)):
        app.busy = True

        # Simulate ActionStep with code parsing error
        err_msg = (
            "Error in code parsing:\n"
            "Your code snippet is invalid, because the regex pattern <code>(.*?)</code> was not found in it."
        )
        step = ActionStep(
            step_number=1,
            error=AgentParsingError(err_msg, MagicMock()),
            timing=Timing(start_time=0.0, end_time=1.2),
        )

        app._render_agent_event(step)

        # Ensure NO 'Tool > 错误' entry was added to transcript
        error_entries = [e for e in app.transcript if "Tool > 错误" in e]
        assert len(error_entries) == 0
        assert "等待恢复" in app._current_activity
        assert any("本步骤未执行代码" in e for e in app.transcript)


@pytest.mark.asyncio
async def test_p2_action_step_preserves_genuine_tool_error(tmp_path: Path) -> None:
    """P2: Verify genuine tool errors (e.g. FileNotFoundError) are still cleanly rendered as Tool > 错误."""
    store = WorkspaceStore(tmp_path / "config.json", tmp_path)
    app = LocalCodeAgentApp(workspace_store=store)
    async with app.run_test(size=(80, 24)):
        app.busy = True

        step = ActionStep(
            step_number=1,
            error=FileNotFoundError("文件不存在：test.txt"),
            timing=Timing(start_time=0.0, end_time=0.5),
        )

        app._render_agent_event(step)

        error_entries = [e for e in app.transcript if "Tool > 错误" in e]
        assert len(error_entries) == 1
        assert "文件不存在：test.txt" in error_entries[0]
