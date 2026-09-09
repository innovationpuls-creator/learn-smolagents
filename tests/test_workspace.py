from pathlib import Path

import pytest
from textual.widgets import Input

from learn_smolagents.agent import SmolAgentRunner
from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.workspaces import DeleteWorkspaceScreen, WorkspaceManager
from learn_smolagents.workspace import Workspace, WorkspaceStore


def make_store(tmp_path):
    initial = tmp_path / "first"
    initial.mkdir()
    return WorkspaceStore(tmp_path / "settings" / "workspaces.json", initial)


def test_create_switch_and_reload(tmp_path):
    store = make_store(tmp_path)
    created = store.open(str(tmp_path / "nested" / "second"), create=True)
    assert created.is_dir()
    assert WorkspaceStore(store.config_path).current == created
    store.open(str(store.paths[0]))
    assert WorkspaceStore(store.config_path).current == store.paths[0]
    with pytest.raises(FileExistsError):
        store.open(str(created), create=True)
    with pytest.raises(ValueError):
        store.open("relative")


def test_delete_requires_exact_confirmation_and_removes_files(tmp_path):
    store = make_store(tmp_path)
    root = store.open(str(tmp_path / "second"), create=True)
    (root / "real.txt").write_text("content")
    store.delete(root, "second")
    assert not root.exists()
    assert store.current is None
    assert WorkspaceStore(store.config_path).current is None


def test_delete_protects_program_and_home(tmp_path):
    store = make_store(tmp_path)
    for path in (Path.cwd(), Path.home(), Path("/"), store.config_path.parent):
        store.open(str(path))
        with pytest.raises(ValueError):
            store.delete(path.resolve(), str(path.resolve()))
        assert path.is_dir()


def test_context_tracks_selection_and_resolves_external_paths(tmp_path):
    store = make_store(tmp_path)
    context = Workspace(store.current)
    assert context.resolve("file.txt") == store.current / "file.txt"
    assert context.resolve("../outside") == tmp_path / "outside"
    assert context.resolve(str(tmp_path)) == tmp_path
    (store.current / "link").symlink_to(tmp_path, target_is_directory=True)
    assert context.resolve("link/file") == tmp_path / "file"
    context.root = store.open(str(tmp_path / "second"), create=True)
    assert context.resolve("file.txt") == store.current / "file.txt"


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(100, 32), (48, 18)])
async def test_manager_create_switch_delete_and_resume(tmp_path, size):
    store = make_store(tmp_path)
    app = LocalCodeAgentApp(workspace_store=store)
    async with app.run_test(size=size) as pilot:
        app._append("You", "old workspace")
        old_agent = app.agent
        app.query_one("#prompt").value = "draft"
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert isinstance(app.screen, WorkspaceManager)
        new_path = tmp_path / "created"
        app.screen.query_one("#workspace-path", Input).value = str(new_path)
        await pilot.click("#create-workspace")
        await pilot.pause()
        assert new_path.is_dir()
        assert app.workspace.root == new_path
        assert isinstance(app.agent, SmolAgentRunner)
        assert app.agent is not old_agent
        assert app.agent.workspace is app.workspace
        assert not app.transcript
        assert app.query_one("#prompt").value == "draft"
        await pilot.press("ctrl+w")
        await pilot.pause()
        await pilot.click("#delete-workspace")
        await pilot.pause()
        assert isinstance(app.screen, DeleteWorkspaceScreen)
        app.screen.query_one("#delete-name", Input).value = new_path.name
        await pilot.click("#confirm-delete")
        await pilot.pause()
        assert not new_path.exists()
        assert app.workspace.root is None
        await pilot.press("enter")
        assert not app.busy
        assert app.query_one("#prompt").value == "draft"


@pytest.mark.asyncio
async def test_manager_disabled_while_busy(tmp_path):
    app = LocalCodeAgentApp(workspace_store=make_store(tmp_path))
    async with app.run_test() as pilot:
        app.busy = True
        await pilot.press("ctrl+w")
        assert not isinstance(app.screen, WorkspaceManager)
        app.busy = False


@pytest.mark.asyncio
async def test_manager_resize_and_cancel(tmp_path):
    app = LocalCodeAgentApp(workspace_store=make_store(tmp_path))
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.press("ctrl+w")
        await pilot.resize_terminal(48, 18)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, WorkspaceManager)
        assert app.query_one("#prompt").has_focus
        assert app.screen.has_class("compact")


def test_program_protection_survives_module_move(tmp_path, monkeypatch):
    import shutil

    from learn_smolagents.workspace import store as store_module

    package = tmp_path / "package"
    module = package / "workspace" / "store.py"
    module.parent.mkdir(parents=True)
    module.touch()
    monkeypatch.setattr(store_module, "__file__", str(module))
    removed = []
    monkeypatch.setattr(shutil, "rmtree", lambda path: removed.append(path))
    store = make_store(tmp_path)
    store.open(str(package))
    with pytest.raises(ValueError, match="不能删除程序"):
        store.delete(package, package.name)
    assert not removed
