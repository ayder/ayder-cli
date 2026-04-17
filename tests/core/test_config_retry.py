"""Config: [retry] section parses into RetryConfigSection with defaults."""
import tomllib
from io import BytesIO

import pytest

from ayder_cli.core.config import Config, RetryConfigSection


def test_retry_section_defaults():
    cfg = Config()
    assert cfg.retry.enabled is True
    assert cfg.retry.max_attempts == 3
    assert cfg.retry.initial_delay_seconds == 0.5
    assert cfg.retry.max_delay_seconds == 30.0
    assert cfg.retry.backoff_coefficient == 2.0
    assert cfg.retry.jitter is True
    assert cfg.retry.retry_on_names == ()


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
