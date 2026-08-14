"""Config should log an actionable error when a provider/driver is misconfigured."""
import pytest
from pydantic import ValidationError

from ayder_cli.core.config import Config


def test_missing_provider_profile_logs_error(loguru_caplog):
    """A provider with no matching [llm.<provider>] profile logs an error and
    still falls back to the openai driver (so the run does not silently misroute
    without any trace)."""
    data = {
        "app": {"provider": "ollama_cloud"},
        "llm": {"ollama": {"driver": "ollama", "model": "m"}},
    }
    cfg = Config(**data)

    assert cfg.driver == "openai"  # silent fallback — now logged
    text = loguru_caplog.at_level("ERROR").text
    assert "ollama_cloud" in text
    assert "ollama" in text  # names the available profile / section to add


def test_valid_provider_profile_logs_no_error(loguru_caplog):
    """A provider that has a matching profile must not log an error."""
    data = {
        "app": {"provider": "ollama"},
        "llm": {"ollama": {"driver": "ollama", "model": "m"}},
    }
    cfg = Config(**data)

    assert cfg.driver == "ollama"
    assert loguru_caplog.at_level("ERROR").text == ""


def test_invalid_driver_logs_error(loguru_caplog):
    """An unsupported driver name logs an error before raising."""
    with pytest.raises(ValidationError):
        Config(driver="not_a_real_driver", provider="openai")

    assert "not_a_real_driver" in loguru_caplog.at_level("ERROR").text
