from ayder_cli.providers import ProviderUnavailableError


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
