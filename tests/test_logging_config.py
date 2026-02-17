"""Tests for logging configuration helpers."""

import logging
from io import StringIO
from unittest.mock import patch

import pytest

from ayder_cli.core.config import Config
from ayder_cli.logging_config import (
    get_effective_log_level,
    is_logging_configured,
    setup_logging,
)


def test_setup_logging_defaults_to_none_when_unset():
    cfg = Config(logging_level=None, logging_file_enabled=False)
    level = setup_logging(cfg)
    assert level == "NONE"
    assert get_effective_log_level() == "NONE"
    assert is_logging_configured() is True


def test_setup_logging_with_override_uses_given_level():
    cfg = Config(logging_level=None, logging_file_enabled=False)
    level = setup_logging(cfg, level_override="debug", console_stream=StringIO())
    assert level == "DEBUG"
    assert get_effective_log_level() == "DEBUG"


def test_setup_logging_without_console_stream_uses_file_sink_only(tmp_path):
    log_file = tmp_path / "ayder.log"
    cfg = Config(
        logging_level=None,
        logging_file_enabled=True,
        logging_file_path=str(log_file),
    )
    with patch("ayder_cli.logging_config.logger.add", return_value=1) as mock_add:
        level = setup_logging(cfg, level_override="INFO")

    assert level == "INFO"
    assert mock_add.call_count == 1
    assert mock_add.call_args.args[0] == str(log_file)


def test_setup_logging_creates_relative_log_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config(
        logging_level=None,
        logging_file_enabled=True,
        logging_file_path=".ayder/log/ayder.log",
    )
    with patch("ayder_cli.logging_config.logger.add", return_value=1):
        setup_logging(cfg, level_override="INFO")

    assert (tmp_path / ".ayder" / "log").exists()


def test_setup_logging_rejects_invalid_level():
    cfg = Config(logging_level=None, logging_file_enabled=False)
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logging(cfg, level_override="trace")


def test_setup_logging_installs_stdlib_interceptor():
    cfg = Config(logging_level=None, logging_file_enabled=False)
    setup_logging(cfg, level_override="INFO", console_stream=StringIO())
    handler_types = {type(h).__name__ for h in logging.getLogger().handlers}
    assert "_InterceptHandler" in handler_types


def test_setup_logging_fallbacks_when_enqueue_fd_is_invalid():
    cfg = Config(logging_level=None, logging_file_enabled=False)
    with patch("ayder_cli.logging_config.logger.add") as mock_add:
        mock_add.side_effect = [ValueError("bad value(s) in fds_to_keep"), 1]
        level = setup_logging(cfg, level_override="DEBUG", console_stream=StringIO())

    assert level == "DEBUG"
    assert mock_add.call_count == 2
    assert mock_add.call_args_list[0].kwargs["enqueue"] is True
    assert mock_add.call_args_list[1].kwargs["enqueue"] is False
