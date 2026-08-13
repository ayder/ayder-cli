"""Tests for logging configuration helpers."""

import logging
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from ayder_cli.logging_config import (
    LoggingSettings,
    get_effective_log_level,
    is_logging_configured,
    setup_logging,
)


def _settings(tmp_path: Path, **kw) -> LoggingSettings:
    """Local to this file. All seven rewritten tests use it."""
    base = dict(
        file_path=str(tmp_path / "ayder.log"),
        error_path=str(tmp_path / "errors.log"),
        trace_path=str(tmp_path / "trace.jsonl"),
    )
    base.update(kw)
    return LoggingSettings(**base)


def test_setup_logging_defaults_to_none_when_unset():
    level = setup_logging(LoggingSettings(file_enabled=False))
    assert level == "NONE"
    assert get_effective_log_level() == "NONE"
    assert is_logging_configured() is True


def test_setup_logging_with_override_uses_given_level():
    level = setup_logging(LoggingSettings(level="DEBUG", file_enabled=False,
                                          console=True, console_stream=StringIO()))
    assert level == "DEBUG"
    assert get_effective_log_level() == "DEBUG"


def test_file_logging_installs_the_error_sink_and_the_narrative_sink(tmp_path):
    """§C5: error_path is added first and is not gated by level."""
    with patch("ayder_cli.logging_config.logger.add", return_value=1) as mock_add:
        level = setup_logging(_settings(tmp_path, level="INFO"))

    assert level == "INFO"
    assert mock_add.call_count == 2, "expected errors.log AND ayder.log"
    paths = [c.args[0] for c in mock_add.call_args_list]
    assert paths[0] == str(tmp_path / "errors.log"), "error sink must be added first"
    assert paths[1] == str(tmp_path / "ayder.log")


def test_setup_logging_creates_relative_log_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("ayder_cli.logging_config.logger.add", return_value=1):
        setup_logging(LoggingSettings(level="INFO", file_path=".ayder/log/ayder.log"))

    assert (tmp_path / ".ayder" / "log").exists()


def test_setup_logging_rejects_invalid_level(tmp_path):
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logging(_settings(tmp_path, level="LOUD"))


def test_setup_logging_installs_stdlib_interceptor():
    setup_logging(LoggingSettings(level="INFO", file_enabled=False,
                                  console=True, console_stream=StringIO()))
    handler_types = {type(h).__name__ for h in logging.getLogger().handlers}
    assert "_InterceptHandler" in handler_types


def test_setup_logging_fallbacks_when_enqueue_fd_is_invalid():
    """§C5: console sink only (file_enabled=False) — the retry pair, not two sinks."""
    with patch("ayder_cli.logging_config.logger.add") as mock_add:
        mock_add.side_effect = [ValueError("bad value(s) in fds_to_keep"), 1]
        level = setup_logging(LoggingSettings(level="DEBUG", file_enabled=False,
                                              console=True, console_stream=StringIO()))

    assert level == "DEBUG"
    assert mock_add.call_count == 2
    assert mock_add.call_args_list[0].kwargs["enqueue"] is True
    assert mock_add.call_args_list[1].kwargs["enqueue"] is False
