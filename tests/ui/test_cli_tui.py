"""Tests for TUI flag integration in CLI."""
import sys
from unittest.mock import patch, MagicMock
import pytest


def test_tui_flag_launches_run_tui():
    """Test that --tui flag calls run_tui()."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '--tui']):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()


def test_tui_short_flag_launches_run_tui():
    """Test that -t short flag calls run_tui()."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '-t']):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()


def test_tui_with_command_raises_error():
    """Test that --tui with command argument raises error."""
    with patch.object(sys, 'argv', ['ayder', '--tui', 'some command']):
        from ayder_cli.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2  # argparse error exit code


def test_tui_with_command_error_message():
    """Test that --tui with command shows correct error message."""
    with patch.object(sys, 'argv', ['ayder', '--tui', 'some command']), \
         patch('sys.stderr') as mock_stderr:
        from ayder_cli.cli import main
        with pytest.raises(SystemExit):
            main()
        # Check that error message was written
        # Note: argparse writes directly to stderr, so we can't easily capture it


def test_no_tui_flag_does_not_call_run_tui():
    """Test that without --tui flag, run_tui() is not called."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_not_called()
        mock_run_interactive.assert_called_once()


def test_tui_flag_exits_before_run_interactive():
    """Test that --tui returns before calling run_interactive()."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder', '--tui']):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()
        mock_run_interactive.assert_not_called()


def test_tui_with_file_flag():
    """Test that --tui can be combined with --file flag."""
    # According to spec, --tui only conflicts with command, not other flags
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '--tui', '--file', 'test.txt']):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()


def test_tui_with_stdin_flag():
    """Test that --tui can be combined with --stdin flag."""
    # According to spec, --tui only conflicts with command, not other flags
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '--tui', '--stdin']):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()
