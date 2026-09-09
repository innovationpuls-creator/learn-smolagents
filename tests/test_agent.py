from __future__ import annotations

from learn_smolagents.agent import runtime as agent_module


def test_runner_creates_one_agent_and_reuses_it(monkeypatch) -> None:
    created_models: list[object] = []
    created_agents: list[object] = []

    class FakeModel:
        def __init__(self, **kwargs: object) -> None:
            created_models.append(kwargs)

    class FakeCodeAgent:
        def __init__(self, **kwargs: object) -> None:
            created_agents.append(self)

        def run(self, prompt: str, **kwargs: object) -> str:
            return f"handled: {prompt}"

    monkeypatch.setattr(agent_module, "OpenAIModel", FakeModel)
    monkeypatch.setattr(agent_module, "CodeAgent", FakeCodeAgent)

    runner = agent_module.SmolAgentRunner(
        config=agent_module.LLMConfig(
            "test-model", "https://example.com/v1", "test-key"
        )
    )

    assert runner.run("first task") == "handled: first task"
    assert runner.run("second task") == "handled: second task"
    assert len(created_models) == 1
    assert len(created_agents) == 1
