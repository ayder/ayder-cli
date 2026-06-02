from types import SimpleNamespace

from ayder_cli.tui import commands
from ayder_cli.providers import ProviderUnavailableError


def test_switch_to_unavailable_provider_keeps_current_state(monkeypatch):
    sentinel_llm = object()
    old_config = SimpleNamespace(model="old-model")
    app = SimpleNamespace(
        config=old_config,
        llm=sentinel_llm,
        chat_loop=SimpleNamespace(llm=sentinel_llm, config=SimpleNamespace(model="old-model", num_ctx=1)),
    )
    messages = []
    chat_view = SimpleNamespace(add_system_message=messages.append)

    monkeypatch.setattr(commands, "load_config_for_provider", lambda p: SimpleNamespace(model="new", num_ctx=2), raising=False)

    def boom(_cfg):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(commands.provider_orchestrator, "create", boom, raising=False)

    commands._apply_provider_switch(app, "anthropic", chat_view)

    assert app.config is old_config          # not mutated
    assert app.llm is sentinel_llm           # not swapped
    assert messages and "pip install ayder-cli[anthropic]" in messages[0]
