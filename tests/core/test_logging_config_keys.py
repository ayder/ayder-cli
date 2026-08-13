import tomllib

import pytest
from pydantic import ValidationError

from ayder_cli.core.config import DEFAULTS, Config
from ayder_cli.core.config_migration import render_v2_config


def test_trace_is_an_accepted_level():
    cfg = Config(provider="openai", model="m", logging_level="TRACE")
    assert cfg.logging_level == "TRACE"


def test_invalid_level_is_rejected_and_message_lists_trace():
    with pytest.raises(ValidationError) as exc:
        Config(provider="openai", model="m", logging_level="LOUD")
    assert "TRACE" in str(exc.value)


def test_new_logging_fields_have_defaults():
    cfg = Config(provider="openai", model="m")
    assert cfg.logging_error_path == ".ayder/log/errors.log"
    assert cfg.logging_trace_path == ".ayder/log/trace.jsonl"
    assert cfg.logging_trace_enabled is False
    assert cfg.logging_channels == {}


def test_channel_keys_accept_external():
    cfg = Config(provider="openai", model="m",
                 logging_channels={"llm": "TRACE", "external": "ERROR"})
    assert cfg.logging_channels["external"] == "ERROR"


def test_unknown_channel_key_is_rejected_by_name():
    with pytest.raises(ValidationError) as exc:
        Config(provider="openai", model="m", logging_channels={"bogus": "INFO"})
    assert "bogus" in str(exc.value)


def test_invalid_channel_level_is_rejected_by_name():
    with pytest.raises(ValidationError) as exc:
        Config(provider="openai", model="m", logging_channels={"llm": "LOUD"})
    assert "LOUD" in str(exc.value)


def test_rendered_config_has_the_new_logging_keys():
    data = tomllib.loads(render_v2_config(DEFAULTS))
    assert data["logging"]["error_path"] == ".ayder/log/errors.log"
    assert data["logging"]["trace_enabled"] is False
    assert data["logging"]["trace_path"] == ".ayder/log/trace.jsonl"
    assert data["logging"]["channels"] == {}


def test_render_preserves_existing_channel_overrides():
    """A migration must be lossless — an empty table would drop these."""
    out = render_v2_config(
        DEFAULTS,
        logging_overrides={"channels": {"llm": "TRACE", "external": "ERROR"}},
    )
    data = tomllib.loads(out)
    assert data["logging"]["channels"] == {"llm": "TRACE", "external": "ERROR"}


def test_rendered_config_is_still_valid_toml_end_to_end():
    """`[logging.channels]` must not swallow the sections that follow it."""
    data = tomllib.loads(render_v2_config(DEFAULTS, logging_overrides={"channels": {"ui": "NONE"}}))
    assert "temporal" in data
    assert "timeouts" in data["temporal"]
    assert any(k.startswith("llm") for k in data)
