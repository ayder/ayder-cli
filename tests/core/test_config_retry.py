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
