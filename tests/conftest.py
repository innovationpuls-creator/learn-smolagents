"""Keep every test away from the user's persisted settings."""

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARN_SMOLAGENTS_ENV", "test")
    monkeypatch.setenv("LEARN_SMOLAGENTS_CONFIG_DIR", str(tmp_path / "config"))
