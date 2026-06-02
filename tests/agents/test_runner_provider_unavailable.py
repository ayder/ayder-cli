import asyncio
from types import SimpleNamespace

from ayder_cli.agents import runner as runner_mod
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.providers import ProviderUnavailableError


def test_agent_with_missing_provider_returns_error_summary(monkeypatch):
    def boom(*a, **k):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(runner_mod, "create_agent_runtime", boom)

    agent_config = SimpleNamespace(name="researcher", model=None)
    r = AgentRunner(
        agent_config=agent_config,
        parent_config=SimpleNamespace(),
        project_ctx=SimpleNamespace(),
        process_manager=SimpleNamespace(),
        permissions=set(),
    )

    summary = asyncio.run(r.run("investigate something"))

    assert summary.status == "error"
    assert "pip install ayder-cli[anthropic]" in summary.error
    assert r.status == "error"
