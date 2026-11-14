"""Config: [retry] section parses into RetryConfigSection with defaults."""
import tomllib
from io import BytesIO

import pytest

from ayder_cli.core.config import Config, RetryConfigSection


def test_retry_section_defaults():
    cfg = Config()
    assert cfg.retry.enabled is True
    assert cfg.retry.max_attempts == 6
    assert cfg.retry.initial_delay_seconds == 10.0
    assert cfg.retry.max_delay_seconds == 30.0
    assert cfg.retry.backoff_coefficient == 2.0
    assert cfg.retry.jitter is True
    assert cfg.retry.retry_on_names == ()


def test_retry_defaults_without_retry_table_in_toml():
    toml = b"""
config_version = "2.0"
[app]
provider = "openai"

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "x"
num_ctx = 8192
"""
    cfg = Config(**tomllib.load(BytesIO(toml)))
    assert cfg.retry.enabled is True
    assert cfg.retry.max_attempts == 6
    assert cfg.retry.initial_delay_seconds == 10.0


def test_first_run_config_loads_with_new_retry_defaults(tmp_path, monkeypatch):
    """A config file generated on first run has no [retry] table, so the
    section defaults apply."""
    from ayder_cli.core import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.toml")
    cfg = config_module.load_config()
    assert cfg.retry.max_attempts == 6
    assert cfg.retry.initial_delay_seconds == 10.0


def test_retry_section_and_runtime_config_defaults_agree():
    from ayder_cli.providers.retry import RetryConfig

    section = RetryConfigSection()
    runtime = RetryConfig()
    assert section.max_attempts == runtime.max_attempts
    assert section.initial_delay_seconds == runtime.initial_delay_seconds
    assert section.max_delay_seconds == runtime.max_delay_seconds
    assert section.backoff_coefficient == runtime.backoff_coefficient
    assert section.jitter == runtime.jitter


def test_retry_section_parses_from_toml():
    toml = b"""
config_version = "2.0"
[app]
provider = "openai"

[retry]
enabled = false
max_attempts = 5
initial_delay_seconds = 1.0
max_delay_seconds = 60.0
backoff_coefficient = 3.0
jitter = false
retry_on_names = ["openai.BadGatewayError", "MyCustomTransientError"]

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "x"
num_ctx = 8192
"""
    data = tomllib.load(BytesIO(toml))
    cfg = Config(**data)
    assert cfg.retry.enabled is False
    assert cfg.retry.max_attempts == 5
    assert cfg.retry.initial_delay_seconds == 1.0
    assert cfg.retry.max_delay_seconds == 60.0
    assert cfg.retry.backoff_coefficient == 3.0
    assert cfg.retry.jitter is False
    assert cfg.retry.retry_on_names == (
        "openai.BadGatewayError",
        "MyCustomTransientError",
    )


def test_retry_section_rejects_non_positive_attempts():
    with pytest.raises(Exception):  # pydantic ValidationError
        RetryConfigSection(max_attempts=0)


def test_retry_section_rejects_coefficient_below_one():
    with pytest.raises(Exception):
        RetryConfigSection(backoff_coefficient=0.5)


def _config_with_retry_table(retry_toml: str) -> Config:
    toml = f"""
config_version = "2.0"
[app]
provider = "openai"

[retry]
{retry_toml}

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "x"
num_ctx = 8192
""".encode()
    return Config(**tomllib.load(BytesIO(toml)))


def test_retry_max_delay_alone_caps_default_initial_delay():
    """Only max_delay_seconds set: the default first delay is capped at it, so
    the runtime RetryConfig (max_delay >= initial_delay) can be built."""
    from unittest.mock import MagicMock

    from ayder_cli.application.runtime_factory import _maybe_wrap_with_retry

    cfg = _config_with_retry_table("max_delay_seconds = 5")
    assert cfg.retry.max_delay_seconds == 5.0
    assert cfg.retry.initial_delay_seconds == 5.0
    assert cfg.retry.max_attempts == 6

    wrapped = _maybe_wrap_with_retry(MagicMock(), cfg, None)
    assert wrapped._retry.initial_delay_seconds == 5.0  # type: ignore[attr-defined]
    assert wrapped._retry.max_delay_seconds == 5.0  # type: ignore[attr-defined]


def test_retry_max_delay_above_default_initial_delay_keeps_default_initial():
    cfg = _config_with_retry_table("max_delay_seconds = 60.0")
    assert cfg.retry.max_delay_seconds == 60.0
    assert cfg.retry.initial_delay_seconds == 10.0


def test_retry_explicit_delays_are_kept_as_given():
    cfg = _config_with_retry_table(
        "initial_delay_seconds = 2.0\nmax_delay_seconds = 8.0"
    )
    assert cfg.retry.initial_delay_seconds == 2.0
    assert cfg.retry.max_delay_seconds == 8.0


def test_retry_explicit_inconsistent_delays_load_unchanged():
    """No new load-time validation error: an inconsistent explicit pair is kept
    as written, and only the runtime RetryConfig rejects it, as before."""
    from ayder_cli.providers.retry import RetryConfig

    cfg = _config_with_retry_table(
        "initial_delay_seconds = 20.0\nmax_delay_seconds = 5.0"
    )
    assert cfg.retry.initial_delay_seconds == 20.0
    assert cfg.retry.max_delay_seconds == 5.0
    with pytest.raises(ValueError):
        RetryConfig(
            initial_delay_seconds=cfg.retry.initial_delay_seconds,
            max_delay_seconds=cfg.retry.max_delay_seconds,
        )


def test_retry_explicit_initial_at_default_value_is_not_capped():
    cfg = _config_with_retry_table(
        "initial_delay_seconds = 10.0\nmax_delay_seconds = 5.0"
    )
    assert cfg.retry.initial_delay_seconds == 10.0


def test_retry_delay_defaults_when_neither_is_set():
    cfg = _config_with_retry_table("enabled = true")
    assert cfg.retry.max_attempts == 6
    assert cfg.retry.initial_delay_seconds == 10.0
    assert cfg.retry.max_delay_seconds == 30.0
    assert RetryConfigSection().initial_delay_seconds == 10.0
