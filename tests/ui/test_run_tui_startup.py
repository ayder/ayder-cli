import pytest

import ayder_cli.tui as tui
from ayder_cli.providers import ProviderUnavailableError


def test_run_tui_exits_when_provider_unavailable(monkeypatch, capsys):
    """run_tui() prints the actionable error and raises SystemExit(1)."""
    def boom(*a, **k):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    # run_tui constructs AyderApp (module-global in ayder_cli.tui); patch it to raise.
    monkeypatch.setattr(tui, "AyderApp", boom)

    with pytest.raises(SystemExit) as ei:
        tui.run_tui(permissions=set())
    assert ei.value.code == 1
    assert "pip install ayder-cli[anthropic]" in capsys.readouterr().err
