"""Tests for /logging TUI command."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ayder_cli.core.config import Config
from ayder_cli.tui.commands import handle_logging
from ayder_cli.tui.screens import CLISelectScreen


def _make_app() -> SimpleNamespace:
    return SimpleNamespace(
        config=Config(),
        _logging_level="NONE",
        push_screen=MagicMock(),
    )


def test_handle_logging_invalid_level_shows_error():
    app = _make_app()
    chat_view = MagicMock()

    handle_logging(app, "trace", chat_view)

    chat_view.add_system_message.assert_called_once()
    assert "Invalid level" in chat_view.add_system_message.call_args[0][0]


def test_handle_logging_applies_direct_level():
    app = _make_app()
    chat_view = MagicMock()

    with patch("ayder_cli.tui.commands.setup_logging", return_value="INFO") as mock_setup:
        handle_logging(app, "info", chat_view)

    mock_setup.assert_called_once_with(app.config, level_override="INFO")
    assert app._logging_level == "INFO"
    chat_view.add_system_message.assert_called_once_with(
        "Logging level set to INFO (session only)"
    )


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

    mock_setup.assert_called_once_with(app.config, level_override="DEBUG")
    assert app._logging_level == "DEBUG"
    chat_view.add_system_message.assert_called_once_with(
        "Logging level set to DEBUG (session only)"
    )
