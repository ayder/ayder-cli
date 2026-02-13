"""Tests for TUI/CLI mode integration in CLI."""
import sys
from unittest.mock import patch, MagicMock
import pytest


def test_default_launches_tui():
    """Test that running ayder with no flags launches TUI."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()


def test_default_tui_gets_read_permissions():
    """Test that default TUI launch passes read-only permissions."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        call_kwargs = mock_run_tui.call_args[1]
        assert call_kwargs['permissions'] == {"r"}


def test_tui_with_write_flag_passes_rw_permissions():
    """Test that -w flag passes read+write permissions to TUI."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '-w']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        call_kwargs = mock_run_tui.call_args[1]
        assert call_kwargs['permissions'] == {"r", "w"}


def test_tui_with_write_and_execute_flags():
    """Test that -w -x flags pass all permissions to TUI."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch.object(sys, 'argv', ['ayder', '-w', '-x']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        call_kwargs = mock_run_tui.call_args[1]
        assert call_kwargs['permissions'] == {"r", "w", "x"}


def test_cli_flag_passes_permissions():
    """Test that --cli with -w -x passes permissions to run_interactive."""
    with patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder', '--cli', '-w', '-x']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_interactive.assert_called_once()
        call_kwargs = mock_run_interactive.call_args
        assert call_kwargs[1].get('permissions') == {"r", "w", "x"} or \
               (call_kwargs[0] and {"r", "w", "x"} in call_kwargs[0])


def test_cli_flag_launches_repl():
    """Test that --cli flag calls run_interactive()."""
    with patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder', '--cli']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_interactive.assert_called_once()


def test_cli_flag_does_not_call_tui():
    """Test that --cli flag does not launch TUI."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder', '--cli']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_not_called()
        mock_run_interactive.assert_called_once()


def test_default_does_not_call_run_interactive():
    """Test that without --cli flag, run_interactive() is not called."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch('ayder_cli.cli_runner.run_interactive') as mock_run_interactive, \
         patch.object(sys, 'argv', ['ayder']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        main()
        mock_run_tui.assert_called_once()
        mock_run_interactive.assert_not_called()


def test_command_arg_runs_command_not_tui():
    """Test that a positional command runs run_command, not TUI."""
    with patch('ayder_cli.tui.run_tui') as mock_run_tui, \
         patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run_command, \
         patch.object(sys, 'argv', ['ayder', 'do something']), \
         patch.object(sys.stdin, 'isatty', return_value=True):
        from ayder_cli.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_run_tui.assert_not_called()
        mock_run_command.assert_called_once()
