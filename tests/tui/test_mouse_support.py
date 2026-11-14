"""Mouse support is enabled in the Textual TUI."""

from unittest.mock import MagicMock, patch

from ayder_cli.tui.app import AyderApp


def test_ayder_app_enables_mouse_support():
    assert AyderApp.ENABLE_MOUSE_SUPPORT is True


def test_run_tui_runs_app_with_mouse_enabled(tmp_path, monkeypatch):
    import ayder_cli.tui as tui

    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)  # stderr.log goes here
    with patch("ayder_cli.tui.AyderApp") as MockApp:
        mock_instance = MagicMock()
        mock_instance.return_code = 0  # a bare MagicMock is truthy
        MockApp.return_value = mock_instance
        tui.run_tui()

    mock_instance.run.assert_called_once_with(inline=False, mouse=True)
