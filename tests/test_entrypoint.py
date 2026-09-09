from __future__ import annotations

import main
from learn_smolagents.ui import app as tui_module


def test_main_runs_the_tui(monkeypatch) -> None:
    started: list[bool] = []

    class FakeApp:
        def run(self) -> None:
            started.append(True)

    monkeypatch.setattr(tui_module, "LocalCodeAgentApp", FakeApp)

    main.main()

    assert started == [True]
