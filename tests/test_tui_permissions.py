import asyncio
from unittest.mock import patch

import pytest
from textual.widgets import Input

from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.approval import ApprovalScreen
from learn_smolagents.workspace import WorkspaceStore
from learn_smolagents.tools.filesystem import build_file_tools


@pytest.mark.asyncio
@pytest.mark.parametrize("approve", [True, False])
@pytest.mark.parametrize("size", [(100, 32), (48, 18)])
async def test_external_read_uses_modal(tmp_path, approve, size):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("external content")
    store = WorkspaceStore(tmp_path / "config.json", root)
    app = LocalCodeAgentApp(workspace_store=store)
    async with app.run_test(size=size) as pilot:
        tools = {tool.name: tool for tool in build_file_tools(app.agent.access)}
        with patch("builtins.input", side_effect=AssertionError("terminal input used")):
            task = asyncio.create_task(
                asyncio.to_thread(tools["read_file"], str(outside))
            )
            for _ in range(100):
                if isinstance(app.screen, ApprovalScreen):
                    break
                await pilot.pause(0.01)
            assert isinstance(app.screen, ApprovalScreen)
            assert not task.done()
            await pilot.click("#allow-access" if approve else "#deny-access")
            if approve:
                assert await asyncio.wait_for(task, 2) == "external content"
            else:
                with pytest.raises(PermissionError):
                    await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_mode_and_switch(tmp_path):
    root = tmp_path / "first"
    root.mkdir()
    other = tmp_path / "second"
    other.mkdir()
    (root / "test.txt").write_text("first")
    (other / "test.txt").write_text("second")
    app = LocalCodeAgentApp(
        workspace_store=WorkspaceStore(tmp_path / "config.json", root)
    )
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.click("#permission-mode")
        assert app.agent.access.full_access
        app.workspace_store.open(str(other))
        app._workspace_changed(True)
        assert app.agent.access.full_access
        tools = {t.name: t for t in build_file_tools(app.agent.access)}
        assert tools["read_file"]("test.txt") == "second"
        assert app.agent._agent is None
        await pilot.pause()
        assert app.query_one("#prompt", Input).has_focus


@pytest.mark.asyncio
async def test_exit_rejects_pending_approval(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("content")
    app = LocalCodeAgentApp(workspace_store=WorkspaceStore(tmp_path / "config.json", root))
    async with app.run_test() as pilot:
        tools = {t.name: t for t in build_file_tools(app.agent.access)}
        task = asyncio.create_task(asyncio.to_thread(tools["read_file"], str(outside)))
        for _ in range(100):
            if isinstance(app.screen, ApprovalScreen):
                break
            await pilot.pause(0.01)
        assert isinstance(app.screen, ApprovalScreen)
        app.exit()
    with pytest.raises(PermissionError):
        await asyncio.wait_for(task, 2)
