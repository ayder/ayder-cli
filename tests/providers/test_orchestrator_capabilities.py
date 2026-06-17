import importlib.util
from types import SimpleNamespace

import pytest

from ayder_cli.providers import ProviderUnavailableError
from ayder_cli.providers.orchestrator import (
    ProviderOrchestrator, DriverCapability, _installed,
)


def test_provider_unavailable_error_message_is_ascii_and_actionable():
    err = ProviderUnavailableError(
        "anthropic", "anthropic",
        {"openai": True, "ollama": True, "deepseek": True,
         "anthropic": False, "google": False, "qwen": False, "glm": False},
    )
    msg = str(err)
    assert "the 'anthropic' driver is not installed" in msg
    assert "pip install ayder-cli[anthropic]" in msg
    assert "available:" in msg and "not installed:" in msg
    assert "openai" in msg.split("available:")[1].split("not installed:")[0]
    assert "anthropic" in msg.split("not installed:")[1]
    assert all(ord(c) < 128 for c in msg)
    assert err.driver == "anthropic" and err.extra == "anthropic"


def _hide_optional(monkeypatch):
    """Make all optional SDKs look uninstalled; keep everything else real."""
    real = importlib.util.find_spec
    hidden = {"anthropic", "google.genai", "dashscope", "zhipuai"}

    def fake(name, *a, **k):
        if name in hidden:
            return None
        return real(name, *a, **k)

    monkeypatch.setattr("importlib.util.find_spec", fake)


def test_core_drivers_always_available(monkeypatch):
    _hide_optional(monkeypatch)
    avail = ProviderOrchestrator().available_drivers()
    assert avail["openai"] and avail["ollama"] and avail["deepseek"]
    assert not avail["anthropic"] and not avail["google"]
    assert not avail["qwen"] and not avail["glm"]
    assert "dashscope" not in avail and "zhipu" not in avail


def test_installed_treats_find_spec_exception_as_unavailable(monkeypatch):
    def boom(name, *a, **k):
        raise ValueError("namespace edge case")
    monkeypatch.setattr("importlib.util.find_spec", boom)
    assert _installed("anything") is False
    assert _installed(None) is True


def test_create_raises_provider_unavailable_for_missing_optional(monkeypatch):
    _hide_optional(monkeypatch)
    from ayder_cli.providers import ProviderUnavailableError
    cfg = SimpleNamespace(driver="anthropic")
    with pytest.raises(ProviderUnavailableError) as ei:
        ProviderOrchestrator().create(cfg)
    assert "pip install ayder-cli[anthropic]" in str(ei.value)


def test_alias_resolves_to_same_capability():
    o = ProviderOrchestrator()
    assert o._capabilities["qwen"].provider_path.endswith("qwen.QwenNativeProvider")
    assert o._canonical("dashscope") == "qwen"
    assert o._canonical("zhipu") == "glm"


def test_create_via_alias_uses_user_value_and_canonical_extra(monkeypatch):
    _hide_optional(monkeypatch)
    from ayder_cli.providers import ProviderUnavailableError
    cfg = SimpleNamespace(driver="dashscope")
    with pytest.raises(ProviderUnavailableError) as ei:
        ProviderOrchestrator().create(cfg)
    msg = str(ei.value)
    assert "the 'dashscope' driver is not installed" in msg
    assert "pip install ayder-cli[qwen]" in msg


def test_register_backward_compatible_two_args():
    o = ProviderOrchestrator()
    o.register("custom", "ayder_cli.providers.impl.openai.OpenAIProvider")
    cap = o._capabilities["custom"]
    assert isinstance(cap, DriverCapability) and cap.sdk_module is None


def test_capability_core_driver_both_none_is_valid():
    cap = DriverCapability("pkg.mod.Provider")
    assert cap.sdk_module is None and cap.extra_name is None


def test_capability_optional_driver_both_set_is_valid():
    cap = DriverCapability("pkg.mod.Provider", "some_sdk", "some_extra")
    assert cap.sdk_module == "some_sdk" and cap.extra_name == "some_extra"


def test_capability_sdk_without_extra_is_rejected():
    """An optional driver with no pip extra cannot produce a usable install hint."""
    with pytest.raises(ValueError):
        DriverCapability("pkg.mod.Provider", sdk_module="some_sdk")


def test_capability_extra_without_sdk_is_rejected():
    """A pip extra is meaningless when no SDK module is ever probed."""
    with pytest.raises(ValueError):
        DriverCapability("pkg.mod.Provider", extra_name="some_extra")


def test_command_runner_prints_provider_error_without_double_prefix(monkeypatch, capsys):
    from ayder_cli import cli_runner
    from ayder_cli.providers import ProviderUnavailableError

    def boom(*a, **k):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(cli_runner, "_run_loop", boom)

    runner = cli_runner.CommandRunner(prompt="hi", permissions=set())
    rc = runner.run()
    err = capsys.readouterr().err
    assert rc == 1
    assert "pip install ayder-cli[anthropic]" in err
    assert "Error: Error:" not in err  # no double prefix
