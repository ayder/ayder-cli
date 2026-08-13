"""Tests for /logging TUI command."""

import dataclasses
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ayder_cli.core.config import Config
from ayder_cli.logging_config import LoggingSettings
from ayder_cli.tui.commands import handle_logging
from ayder_cli.tui.screens import CLISelectScreen


def _make_app() -> SimpleNamespace:
    return SimpleNamespace(
        config=Config(),
        _logging_level="NONE",
        _log_settings=LoggingSettings(
            level="NONE",
            channels=frozenset({"llm"}),
            channel_levels={"ui": None, "tool": 10},
            trace_enabled=True,
            console=True,
            console_stream=sys.stdout,
            file_enabled=True,
            rotation="5 MB",
            retention="3 days",
        ),
        push_screen=MagicMock(),
    )


def test_handle_logging_invalid_level_shows_error():
    app = _make_app()
    chat_view = MagicMock()

    handle_logging(app, "LOUD", chat_view)

    chat_view.add_system_message.assert_called_once()
    assert "Invalid level" in chat_view.add_system_message.call_args[0][0]


def test_handle_logging_applies_direct_level():
    app = _make_app()
    chat_view = MagicMock()

    with patch("ayder_cli.tui.commands.setup_logging", return_value="INFO") as mock_setup:
        handle_logging(app, "info", chat_view)

    mock_setup.assert_called_once_with(app._log_settings)
    assert app._log_settings.level == "INFO"
    assert app._logging_level == "INFO"
    chat_view.add_system_message.assert_called_once()
    msg = chat_view.add_system_message.call_args[0][0]
    assert "Logging level set to INFO" in msg
    assert "ayder.log" in msg


def test_handle_logging_opens_select_screen_and_applies_choice():
    app = _make_app()
    chat_view = MagicMock()

    with patch(
        "ayder_cli.tui.commands.setup_logging", return_value="DEBUG"
    ) as mock_setup:
        handle_logging(app, "", chat_view)

        app.push_screen.assert_called_once()
        screen, callback = app.push_screen.call_args[0]
        assert isinstance(screen, CLISelectScreen)

        callback("DEBUG")

    mock_setup.assert_called_once_with(app._log_settings)
    assert app._log_settings.level == "DEBUG"
    assert app._logging_level == "DEBUG"
    chat_view.add_system_message.assert_called_once()
    msg = chat_view.add_system_message.call_args[0][0]
    assert "Logging level set to DEBUG" in msg
    assert "ayder.log" in msg


def test_logging_command_preserves_every_field_except_level():
    app = _make_app()                       # now carries _log_settings
    before = app._log_settings

    # `commands.py` does `from ayder_cli.logging_config import setup_logging`,
    # so the name to patch lives in THIS module. Without the patch a unit test
    # opens real sinks under .ayder/log and mutates process-global loguru state.
    with patch("ayder_cli.tui.commands.setup_logging", return_value="DEBUG"):
        handle_logging(app, "DEBUG", MagicMock())

    after = app._log_settings
    assert after.level == "DEBUG"
    for f in dataclasses.fields(LoggingSettings):
        if f.name == "level":
            continue
        assert getattr(after, f.name) == getattr(before, f.name), f.name
