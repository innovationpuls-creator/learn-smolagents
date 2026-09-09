import stat

import pytest
from textual.widgets import Input

from learn_smolagents.config import LLMConfig, SettingsStore, config_directory
from learn_smolagents.ui.app import LocalCodeAgentApp


def test_settings_roundtrip_and_permissions(tmp_path):
    store = SettingsStore(tmp_path / "llm.json")
    config = LLMConfig("test-model", "https://example.com/v1", "test-key")
    store.save(config)
    assert store.load() == config
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_environment_isolation(monkeypatch):
    directories = []
    for environment in ("development", "test", "production"):
        monkeypatch.setenv("LEARN_SMOLAGENTS_ENV", environment)
        directories.append(config_directory())
    assert len(set(directories)) == 3
    monkeypatch.setenv("LEARN_SMOLAGENTS_ENV", "invalid")
    with pytest.raises(ValueError):
        config_directory()


def test_invalid_settings_do_not_replace_saved_config(tmp_path):
    store = SettingsStore(tmp_path / "llm.json")
    config = LLMConfig("test-model", "https://example.com/v1", "test-key")
    store.save(config)
    with pytest.raises(ValueError):
        store.save(LLMConfig())
    assert store.load() == config


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(80, 24), (60, 24)])
async def test_tui_saves_and_applies_settings(size):
    app = LocalCodeAgentApp()
    original_agent = app.agent
    async with app.run_test(size=size) as pilot:
        await pilot.click("#llm-settings")
        app.screen.query_one("#llm-model", Input).value = "test-model"
        app.screen.query_one("#llm-base", Input).value = "https://example.com/v1"
        app.screen.query_one("#llm-key", Input).value = "test-key"
        assert app.screen.query_one("#llm-key", Input).password
        await pilot.click("#llm-save")
        await pilot.pause()
        assert app.agent is not original_agent
        assert app.agent.config == app.settings_store.load()
        assert app.llm_config.model_id == "test-model"
