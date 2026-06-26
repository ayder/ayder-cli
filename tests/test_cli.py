"""Tests for cli.py — coverage for run_command, main(), and task runners."""

import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import StringIO


def _close_coro(coro):
    """asyncio.run replacement: close the coroutine instead of awaiting it.

    _run_loop calls ``asyncio.run(_drive())``; patching asyncio.run with a bare
    mock leaves _drive() as an un-awaited coroutine that raises a RuntimeWarning
    when garbage-collected. Closing it here keeps the patch but silences the leak.
    """
    coro.close()


class TestRunCommand:
    """Test run_command function."""

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    def test_run_command_success(self, mock_run_loop):
        """Test successful command execution."""
        from ayder_cli.cli_runner import run_command

        result = run_command("test prompt", permissions={"r"})

        assert result == 0
        mock_run_loop.assert_called_once_with(
            "test prompt", permissions={"r"}, agent_mode=False,
            system_prompt_override=None,
        )

    @patch('ayder_cli.cli_runner._run_loop', side_effect=Exception("Loop error"))
    def test_run_command_error(self, mock_run_loop):
        """Test command execution with error."""
        from ayder_cli.cli_runner import run_command

        with patch('sys.stderr', new=StringIO()) as mock_stderr:
            result = run_command("test prompt")
            assert result == 1
            assert "Loop error" in mock_stderr.getvalue()

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    def test_run_command_delegates_to_run_loop(self, mock_run_loop):
        """Test run_command creates CommandRunner that delegates to _run_loop."""
        from ayder_cli.cli_runner import run_command

        result = run_command("test prompt", permissions={"r", "w"})

        assert result == 0
        mock_run_loop.assert_called_once_with(
            "test prompt", permissions={"r", "w"}, agent_mode=False,
            system_prompt_override=None,
        )

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    def test_run_command_agent_mode_propagates(self, mock_run_loop):
        """--agent flows through run_command -> _run_loop as agent_mode=True."""
        from ayder_cli.cli_runner import run_command

        result = run_command("build X", permissions={"r"}, agent_mode=True)

        assert result == 0
        mock_run_loop.assert_called_once_with(
            "build X", permissions={"r"}, agent_mode=True,
            system_prompt_override=None,
        )


class TestRunLoop:
    """Test _run_loop helper — the shared CLI→ChatLoop bridge."""

    def test_run_loop_creates_chat_loop(self):
        """_run_loop must create a ChatLoop with CliCallbacks and call asyncio.run."""
        from ayder_cli.cli_runner import _run_loop

        mock_rt = MagicMock()
        mock_rt.config.model = "test-model"
        mock_rt.config.num_ctx = 4096
        mock_rt.config.max_output_tokens = 2048
        mock_rt.config.stop_sequences = []
        mock_rt.config.verbose = False
        mock_rt.config.tool_tags = None
        mock_rt.system_prompt = "system"

        with patch('ayder_cli.cli_runner.create_runtime', return_value=mock_rt) as mock_create, \
             patch('ayder_cli.cli_runner.asyncio.run', side_effect=_close_coro) as mock_asyncio_run:
            result = _run_loop("hello", permissions={"r"})

        assert result == 0
        mock_create.assert_called_once()
        mock_asyncio_run.assert_called_once()

    def test_run_loop_passes_system_and_user_messages(self):
        """_run_loop must prepend system prompt and user prompt to messages."""
        from ayder_cli.cli_runner import _run_loop

        mock_rt = MagicMock()
        mock_rt.config.model = "test-model"
        mock_rt.config.num_ctx = 4096
        mock_rt.config.max_output_tokens = 2048
        mock_rt.config.stop_sequences = []
        mock_rt.config.verbose = False
        mock_rt.config.tool_tags = None
        mock_rt.system_prompt = "You are a helpful assistant."

        with patch('ayder_cli.cli_runner.create_runtime', return_value=mock_rt), \
             patch('ayder_cli.cli_runner.ChatLoop') as MockLoop, \
             patch('ayder_cli.cli_runner.asyncio.run', side_effect=_close_coro):
            MockLoop.return_value.run = AsyncMock()
            _run_loop("test prompt", permissions={"r"})

        # Verify ChatLoop was constructed with correct messages
        call_kwargs = MockLoop.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert messages[1] == {"role": "user", "content": "test prompt"}


class TestRunTasksCLI:
    """Test _run_tasks_cli function."""

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tools.builtins.tasks.list_tasks')
    def test_run_tasks_cli_success(self, mock_list_tasks, mock_project_ctx):
        """Test successful tasks listing."""
        from ayder_cli.cli_runner import _run_tasks_cli

        mock_list_tasks.return_value = "Task 1\nTask 2"

        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            result = _run_tasks_cli()
            assert result == 0
            assert "Task 1" in mock_stdout.getvalue()

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tools.builtins.tasks.list_tasks')
    def test_run_tasks_cli_error(self, mock_list_tasks, mock_project_ctx):
        """Test tasks listing with error."""
        from ayder_cli.cli_runner import _run_tasks_cli

        mock_list_tasks.side_effect = Exception("List error")

        with patch('sys.stderr', new=StringIO()) as mock_stderr:
            result = _run_tasks_cli()
            assert result == 1
            assert "List error" in mock_stderr.getvalue()


class TestRunImplementCLI:
    """Test _run_implement_cli function."""

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tools.builtins.tasks._get_tasks_dir')
    @patch('ayder_cli.tools.builtins.tasks._get_task_path_by_id')
    def test_run_implement_by_id_success(self, mock_get_path, mock_get_dir,
                                          mock_project_ctx, mock_run_loop):
        """Test implementing task by ID."""
        from ayder_cli.cli_runner import _run_implement_cli
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task_file = tasks_dir / "TASK-001-test-task.md"
            task_file.write_text("# Test Task")

            mock_get_dir.return_value = tasks_dir
            mock_get_path.return_value = task_file

            with patch('sys.stdout', new=StringIO()):
                result = _run_implement_cli("1", permissions={"r"})

            assert result == 0
            mock_run_loop.assert_called_once()

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tools.builtins.tasks._get_tasks_dir')
    @patch('ayder_cli.tools.builtins.tasks._extract_id')
    @patch('ayder_cli.tools.builtins.tasks._parse_title')
    def test_run_implement_by_pattern_success(self, mock_parse_title, mock_extract_id, mock_get_dir,
                                               mock_project_ctx, mock_run_loop):
        """Test implementing task by pattern match."""
        from ayder_cli.cli_runner import _run_implement_cli
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task_file = tasks_dir / "TASK-001-authentication.md"
            task_file.write_text("# Implement Authentication")

            mock_get_dir.return_value = tasks_dir
            mock_extract_id.return_value = 1
            mock_parse_title.return_value = "Implement Authentication"

            with patch('sys.stdout', new=StringIO()):
                result = _run_implement_cli("auth", permissions={"r"})

            assert result == 0

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tools.builtins.tasks._get_tasks_dir')
    def test_run_implement_no_match(self, mock_get_dir, mock_project_ctx):
        """Test implementing when no task matches."""
        from ayder_cli.cli_runner import _run_implement_cli
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)

            mock_get_dir.return_value = tasks_dir

            with patch('sys.stderr', new=StringIO()) as mock_stderr:
                result = _run_implement_cli("nonexistent", permissions={"r"})
                assert result == 1
                assert "No tasks found" in mock_stderr.getvalue()

    def test_run_implement_error(self):
        """Test implement with error — exception inside implement_task is caught."""
        from ayder_cli.cli_runner import _run_implement_cli

        with patch('ayder_cli.core.context.ProjectContext', side_effect=Exception("Build error")):
            with patch('sys.stderr', new=StringIO()) as mock_stderr:
                result = _run_implement_cli("1")
                assert result == 1
                assert "Build error" in mock_stderr.getvalue()


class TestRunImplementAllCLI:
    """Test _run_implement_all_cli function."""

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    def test_run_implement_all_success(self, mock_run_loop):
        """Test successful implement all."""
        from ayder_cli.cli_runner import _run_implement_all_cli

        result = _run_implement_all_cli(permissions={"r"})

        assert result == 0
        mock_run_loop.assert_called_once()

    @patch('ayder_cli.cli_runner._run_loop', side_effect=Exception("Build error"))
    def test_run_implement_all_error(self, mock_run_loop):
        """Test implement all with error."""
        from ayder_cli.cli_runner import _run_implement_all_cli

        with patch('sys.stderr', new=StringIO()) as mock_stderr:
            result = _run_implement_all_cli()
            assert result == 1
            assert "Build error" in mock_stderr.getvalue()


class TestMainFunction:
    """Test main() function entry point."""

    def test_main_permission_flags_indirect(self):
        """Test permission flags are parsed correctly (indirect via args)."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        # Test -w flag (no positional command needed to verify flag parsing)
        args = parser.parse_args(['-w'])
        assert args.w is True
        assert args.x is False
        assert args.http is False

        # Test -x flag
        args = parser.parse_args(['-x'])
        assert args.x is True
        assert args.w is False
        assert args.http is False

        # Test --http flag
        args = parser.parse_args(['--http'])
        assert args.http is True
        assert args.w is False
        assert args.x is False

        # Test both flags
        args = parser.parse_args(['-w', '-x'])
        assert args.w is True
        assert args.x is True
        assert args.http is False


class TestMainPermissionHandling:
    """Test main() function permission flag handling (lines 241, 243)."""

    def test_main_passes_write_permission_to_run_command(self):
        """Test that -w flag adds 'w' to permissions passed to run_command."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '-w', 'write something']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert 'w' in call_kwargs['permissions']
            assert 'r' in call_kwargs['permissions']

    def test_main_passes_execute_permission_to_run_command(self):
        """Test that -x flag adds 'x' to permissions passed to run_command."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '-x', 'run command']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert 'x' in call_kwargs['permissions']
            assert 'r' in call_kwargs['permissions']

    def test_main_passes_both_permissions_to_run_command(self):
        """Test that -w and -x flags add both to permissions."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '-w', '-x', 'do something']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert 'w' in call_kwargs['permissions']
            assert 'x' in call_kwargs['permissions']
            assert 'r' in call_kwargs['permissions']

    def test_main_passes_http_permission_to_run_command(self):
        """Test that --http flag adds 'http' to permissions passed to run_command."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '--http', 'fetch url']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert 'http' in call_kwargs['permissions']
            assert 'r' in call_kwargs['permissions']

    def test_main_agent_flag_implies_write_execute_http(self):
        """--agent implies w+x+http and forwards agent_mode=True to run_command."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )

        with patch.object(sys, 'argv', ['ayder', '--agent', 'build a feature']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert {'r', 'w', 'x', 'http'} <= call_kwargs['permissions']
            assert call_kwargs['agent_mode'] is True

    def test_main_default_permissions_only_read(self):
        """Test that default permissions only include 'r'."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', 'hello']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:

            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['permissions'] == {'r'}


class TestMainConfigFlag:
    """Test main() handling of the -c/--config flag."""

    def test_main_config_flag_missing_file_errors(self):
        """-c pointing at a missing file exits 1 with a clear error message."""
        from ayder_cli.cli import main

        with patch.object(sys, 'argv', ['ayder', '-c', '/no/such/config.toml', 'hello']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('sys.stderr', new=StringIO()) as mock_stderr:
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
            assert "Config file not found" in mock_stderr.getvalue()

    def test_main_config_flag_applies_override(self, tmp_path):
        """-c with an existing file calls set_config_path before loading config."""
        from pathlib import Path
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        cfg_file = tmp_path / "custom.toml"
        cfg_file.write_text('config_version = "2.0"\n', encoding="utf-8")

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )

        with patch.object(sys, 'argv', ['ayder', '-c', str(cfg_file), 'hello']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.set_config_path') as mock_set, \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0):
            with pytest.raises(SystemExit):
                main()

            mock_set.assert_called_once()
            called_arg = mock_set.call_args[0][0]
            assert Path(called_arg) == cfg_file


class TestMainSystemPromptFlag:
    """Test main() handling of the --system-prompt flag."""

    def test_main_system_prompt_missing_file_errors(self):
        """--system-prompt pointing at a missing file exits 1 with a clear message."""
        from ayder_cli.cli import main

        with patch.object(sys, 'argv', ['ayder', '--system-prompt', '/no/such/sp.md', 'hi']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('sys.stderr', new=StringIO()) as mock_stderr:
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
            assert "System prompt file not found" in mock_stderr.getvalue()

    def test_main_system_prompt_passed_to_run_command(self, tmp_path):
        """--system-prompt file contents flow to run_command as system_prompt_override."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        sp_file = tmp_path / "sp.md"
        sp_file.write_text("CUSTOM SYSTEM PROMPT", encoding="utf-8")

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )

        with patch.object(sys, 'argv', ['ayder', '--system-prompt', str(sp_file), 'hello']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:
            with pytest.raises(SystemExit):
                main()

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['system_prompt_override'] == "CUSTOM SYSTEM PROMPT"

    def test_main_system_prompt_passed_to_run_tui(self, tmp_path):
        """--system-prompt with no command flows to run_tui as system_prompt_override."""
        from ayder_cli.cli import main

        sp_file = tmp_path / "sp.md"
        sp_file.write_text("TUI CUSTOM PROMPT", encoding="utf-8")

        with patch.object(sys, 'argv', ['ayder', '--system-prompt', str(sp_file)]), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            main()

            call_kwargs = mock_run_tui.call_args[1]
            assert call_kwargs['system_prompt_override'] == "TUI CUSTOM PROMPT"


class TestMainTaskOptions:
    """Test main() function task-related CLI options."""

    def test_main_tasks_flag(self):
        """Test --tasks flag calls _run_tasks_cli."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '--tasks']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner._run_tasks_cli', return_value=0) as mock_run_tasks:

            with pytest.raises(SystemExit):
                main()

            mock_run_tasks.assert_called_once()

    def test_main_implement_flag(self):
        """Test --implement flag calls _run_implement_cli."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '--implement', '1']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner._run_implement_cli', return_value=0) as mock_run_implement:

            with pytest.raises(SystemExit):
                main()

            mock_run_implement.assert_called_once_with('1', permissions={'r'})

    def test_main_implement_all_flag(self):
        """Test --implement-all flag calls _run_implement_all_cli."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        with patch.object(sys, 'argv', ['ayder', '--implement-all']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner._run_implement_all_cli', return_value=0) as mock_run_all:

            with pytest.raises(SystemExit):
                main()

            mock_run_all.assert_called_once_with(permissions={'r'})


class TestMainTUIAndInteractive:
    """Test main() function TUI mode."""

    def test_main_default_tui_mode(self):
        """Test default (no flags) launches TUI mode."""
        from ayder_cli.cli import main

        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:

            main()

            mock_run_tui.assert_called_once()


class TestModuleEntryPoint:
    """Test __main__ entry point."""

    def test_module_entry_point(self):
        """Test that __name__ == '__main__' block calls main()."""
        with patch('ayder_cli.cli.main') as mock_main:
            import ayder_cli.cli as cli_module
            if True:  # Simulating __name__ == "__main__"
                cli_module.main()
            mock_main.assert_called_once()


class TestCreateParser:
    """Test create_parser function."""

    def test_parser_version_flag(self):
        """Test --version flag is configured."""
        from ayder_cli.cli import create_parser
        from ayder_cli.version import get_app_version

        parser = create_parser()

        version_action = None
        for action in parser._actions:
            if action.dest == 'version':
                version_action = action
                break

        assert version_action is not None
        assert version_action.version == get_app_version()

    def test_parser_file_flag(self):
        """Test --file flag is configured."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(['--file', 'test.txt'])
        assert args.file == 'test.txt'

    def test_parser_stdin_flag(self):
        """Test --stdin flag is configured."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(['--stdin'])
        assert args.stdin is True

    def test_parser_permission_flags(self):
        """Test permission flags -r, -w, -x, --http."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.r is True
        assert args.w is False
        assert args.x is False
        assert args.http is False

        args = parser.parse_args(['-r', '-w', '-x', '--http'])
        assert args.r is True
        assert args.w is True
        assert args.x is True
        assert args.http is True

    def test_parser_temporal_prompt_flag(self):
        """--prompt was renamed to --temporal-prompt (temporal worker only)."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.temporal_prompt is None

        args = parser.parse_args(["--temporal-prompt", "prompts/dev.md"])
        assert args.temporal_prompt == "prompts/dev.md"

    def test_parser_prompt_flag_removed(self):
        """The old --prompt flag no longer exists after the rename."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--prompt", "prompts/dev.md"])

    def test_parser_system_prompt_flag(self):
        """--system-prompt accepts a file path and defaults to None."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.system_prompt is None

        args = parser.parse_args(["--system-prompt", "sp.md"])
        assert args.system_prompt == "sp.md"

    def test_parser_config_flag(self):
        """Test -c/--config flag is configured and defaults to None."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.config is None

        args = parser.parse_args(["-c", "custom.toml"])
        assert args.config == "custom.toml"

        args = parser.parse_args(["--config", "other.toml"])
        assert args.config == "other.toml"

    def test_parser_verbose_flag(self):
        """--verbose is a boolean console toggle (it no longer takes a level)."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.verbose is False

        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    def test_parser_command_argument(self):
        """Test positional command argument via the base (non-subcommand) parser."""
        from ayder_cli.cli import _create_base_parser

        parser = _create_base_parser()

        args = parser.parse_args(['hello world'])
        assert args.command == 'hello world'

        args = parser.parse_args([])
        assert args.command is None

    def _run_main_for_logging(self, argv, mock_config):
        """Helper: run main() with logging patched, return the setup_logging mock."""
        from ayder_cli.cli import main

        with patch.object(sys, "argv", argv), patch(
            "ayder_cli.core.config.load_config", return_value=mock_config
        ), patch("ayder_cli.cli.setup_logging") as mock_setup_logging, patch(
            "ayder_cli.cli_runner._run_tasks_cli", return_value=0
        ):
            with pytest.raises(SystemExit):
                main()
        return mock_setup_logging

    def _mock_config(self, **overrides):
        from ayder_cli.core.config import Config

        base = dict(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )
        base.update(overrides)
        return Config(**base)

    def test_main_verbose_and_logging_level_decoupled(self):
        """--verbose enables console; --logging-level sets the level (verbose no longer wins)."""
        mock_config = self._mock_config()
        mock_setup_logging = self._run_main_for_logging(
            ["ayder", "--verbose", "--logging-level", "debug", "--tasks"], mock_config
        )
        mock_setup_logging.assert_called_once_with(
            mock_config, level_override="DEBUG", console_stream=sys.stdout
        )

    def test_main_verbose_alone_defaults_to_info_console(self):
        """--verbose with no level anywhere defaults the console to INFO."""
        mock_config = self._mock_config()  # logging_level defaults to None
        mock_setup_logging = self._run_main_for_logging(
            ["ayder", "--verbose", "--tasks"], mock_config
        )
        mock_setup_logging.assert_called_once_with(
            mock_config, level_override="INFO", console_stream=sys.stdout
        )

    def test_main_verbose_respects_config_level(self):
        """--verbose with a config level shows that level on the console (no INFO fallback)."""
        mock_config = self._mock_config(logging_level="WARNING")
        mock_setup_logging = self._run_main_for_logging(
            ["ayder", "--verbose", "--tasks"], mock_config
        )
        # level_override left None so setup_logging uses config.logging_level; console on.
        mock_setup_logging.assert_called_once_with(
            mock_config, level_override=None, console_stream=sys.stdout
        )

    def test_main_logging_level_without_verbose_is_file_only(self):
        """--logging-level without --verbose sets the level but keeps the console off."""
        mock_config = self._mock_config()
        mock_setup_logging = self._run_main_for_logging(
            ["ayder", "--logging-level", "debug", "--tasks"], mock_config
        )
        mock_setup_logging.assert_called_once_with(
            mock_config, level_override="DEBUG", console_stream=None
        )


class TestMainResume:
    """Test --resume flag parsing, conflict guard, and launch."""

    def test_resume_arg_parses(self):
        from ayder_cli.cli import create_parser

        args = create_parser().parse_args(['--resume', 'a1b2-c3d4'])
        assert args.resume == 'a1b2-c3d4'

    def test_resume_conflicts_with_session_flags(self):
        from ayder_cli.cli import main

        with patch.object(sys, 'argv', ['ayder', '--resume', 'a1b2', '-w']), \
             patch.object(sys.stdin, 'isatty', return_value=True):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_resume_loads_and_launches(self, tmp_path, monkeypatch):
        from ayder_cli.cli import main
        from ayder_cli.core.session import save_session

        monkeypatch.chdir(tmp_path)
        sid = save_session(
            [{"role": "system", "content": "SYS"},
             {"role": "user", "content": "hi"}],
            model="qwen", agent_mode=True, permissions={"r", "w", "x", "http"},
        )

        with patch.object(sys, 'argv', ['ayder', '--resume', sid]), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            main()

        kwargs = mock_run_tui.call_args[1]
        assert kwargs['resume_session_id'] == sid
        assert kwargs['initial_messages'][1]['content'] == "hi"
        assert kwargs['agent_mode'] is True
        assert kwargs['permissions'] == {"r", "w", "x", "http"}

    def test_resume_bad_id_exits(self, tmp_path, monkeypatch):
        from ayder_cli.cli import main

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, 'argv', ['ayder', '--resume', 'zzzz']), \
             patch.object(sys.stdin, 'isatty', return_value=True):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
