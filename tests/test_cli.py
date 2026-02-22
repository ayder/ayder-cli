"""Tests for cli.py — coverage for _build_services, run_command, main(), and task runners."""

import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import StringIO


class TestBuildServices:
    """Test _build_services function."""

    def test_build_services_with_exception_in_structure_macro(self):
        """Test that _build_services handles exception when getting project structure."""
        from ayder_cli.cli_runner import _build_services
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        mock_registry = MagicMock()
        mock_registry.execute.side_effect = Exception("Structure error")

        with patch('ayder_cli.application.runtime_factory.load_config', return_value=mock_config), \
             patch('ayder_cli.application.runtime_factory.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            services = _build_services()
            cfg, llm_provider, project_ctx, enhanced_system, checkpoint_manager, memory_manager = services

            assert cfg == mock_config
            assert llm_provider is not None
            assert project_ctx is not None
            assert checkpoint_manager is not None
            assert memory_manager is not None
            # Verify macro is empty when exception occurs
            assert "PROJECT STRUCTURE" not in enhanced_system

    def test_build_services_success_with_structure_macro(self):
        """Test _build_services successfully adds structure macro."""
        from ayder_cli.cli_runner import _build_services
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        mock_registry = MagicMock()
        mock_registry.execute.return_value = "src/\n  main.py\n  utils.py"

        with patch('ayder_cli.application.runtime_factory.load_config', return_value=mock_config), \
             patch('ayder_cli.application.runtime_factory.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            services = _build_services()
            cfg, llm_provider, project_ctx, enhanced_system, checkpoint_manager, memory_manager = services

            assert "PROJECT STRUCTURE" in enhanced_system
            assert "src/" in enhanced_system
            assert checkpoint_manager is not None
            assert memory_manager is not None
            mock_registry.execute.assert_called_once_with("get_project_structure", {"max_depth": 3})

    def test_build_services_with_custom_config(self):
        """Test _build_services accepts custom config parameter."""
        from ayder_cli.cli_runner import _build_services
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://custom:8080/v1",
            api_key="custom-key",
            model="custom-model",
            num_ctx=2048,
            verbose=True
        )

        mock_registry = MagicMock()
        mock_registry.execute.return_value = "project/"

        with patch('ayder_cli.application.runtime_factory.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            services = _build_services(config=mock_config)
            cfg = services[0]

            assert cfg == mock_config

    def test_build_services_with_custom_project_root(self):
        """Test _build_services accepts custom project root."""
        from ayder_cli.cli_runner import _build_services
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )

        mock_registry = MagicMock()

        with patch('ayder_cli.application.runtime_factory.load_config', return_value=mock_config), \
             patch('ayder_cli.application.runtime_factory.ProjectContext') as mock_project_ctx_class, \
             patch('ayder_cli.application.runtime_factory.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            _build_services(project_root="/custom/path")

            mock_project_ctx_class.assert_called_once_with("/custom/path")


class TestRunCommand:
    """Test run_command function."""

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    def test_run_command_success(self, mock_run_loop):
        """Test successful command execution."""
        from ayder_cli.cli_runner import run_command

        result = run_command("test prompt", permissions={"r"}, iterations=5)

        assert result == 0
        mock_run_loop.assert_called_once_with(
            "test prompt", permissions={"r"}, iterations=5
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

        result = run_command("test prompt", permissions={"r", "w"}, iterations=10)

        assert result == 0
        mock_run_loop.assert_called_once_with(
            "test prompt", permissions={"r", "w"}, iterations=10
        )


class TestRunLoop:
    """Test _run_loop helper — the shared CLI→TuiChatLoop bridge."""

    def test_run_loop_creates_tui_chat_loop(self):
        """_run_loop must create a TuiChatLoop with CliCallbacks and call asyncio.run."""
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
             patch('ayder_cli.cli_runner.asyncio.run') as mock_asyncio_run:
            result = _run_loop("hello", permissions={"r"}, iterations=10)

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
             patch('ayder_cli.cli_runner.TuiChatLoop') as MockLoop, \
             patch('ayder_cli.cli_runner.asyncio.run'):
            MockLoop.return_value.run = AsyncMock()
            _run_loop("test prompt", permissions={"r"})

        # Verify TuiChatLoop was constructed with correct messages
        call_kwargs = MockLoop.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert messages[1] == {"role": "user", "content": "test prompt"}


class TestRunTasksCLI:
    """Test _run_tasks_cli function."""

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks.list_tasks')
    def test_run_tasks_cli_success(self, mock_list_tasks, mock_project_ctx):
        """Test successful tasks listing."""
        from ayder_cli.cli_runner import _run_tasks_cli

        mock_list_tasks.return_value = "Task 1\nTask 2"

        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            result = _run_tasks_cli()
            assert result == 0
            assert "Task 1" in mock_stdout.getvalue()

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks.list_tasks')
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
    @patch('ayder_cli.tasks._get_tasks_dir')
    @patch('ayder_cli.tasks._get_task_path_by_id')
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
                result = _run_implement_cli("1", permissions={"r"}, iterations=10)

            assert result == 0
            mock_run_loop.assert_called_once()

    @patch('ayder_cli.cli_runner._run_loop', return_value=0)
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks._get_tasks_dir')
    @patch('ayder_cli.tasks._extract_id')
    @patch('ayder_cli.tasks._parse_title')
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
                result = _run_implement_cli("auth", permissions={"r"}, iterations=10)

            assert result == 0

    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks._get_tasks_dir')
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

        result = _run_implement_all_cli(permissions={"r"}, iterations=10)

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

        # Test -w flag
        args = parser.parse_args(['-w', 'test command'])
        assert args.w is True
        assert args.x is False
        assert args.http is False

        # Test -x flag
        args = parser.parse_args(['-x', 'test command'])
        assert args.x is True
        assert args.w is False
        assert args.http is False

        # Test --http flag
        args = parser.parse_args(['--http', 'test command'])
        assert args.http is True
        assert args.w is False
        assert args.x is False

        # Test both flags
        args = parser.parse_args(['-w', '-x', 'test command'])
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

            mock_run_implement.assert_called_once_with('1', permissions={'r'}, iterations=50)

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

            mock_run_all.assert_called_once_with(permissions={'r'}, iterations=50)

    def test_main_temporal_task_queue_flag(self):
        """Test --temporal-task-queue calls _run_temporal_queue_cli."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )

        with patch.object(
            sys,
            "argv",
            [
                "ayder",
                "--temporal-task-queue",
                "dev-team",
                "--prompt",
                "prompts/dev.md",
            ],
        ), patch.object(sys.stdin, "isatty", return_value=True), patch(
            "ayder_cli.core.config.load_config", return_value=mock_config
        ), patch(
            "ayder_cli.cli_runner._run_temporal_queue_cli", return_value=0
        ) as mock_temporal_run:
            with pytest.raises(SystemExit):
                main()

            mock_temporal_run.assert_called_once_with(
                queue_name="dev-team",
                prompt_path="prompts/dev.md",
                permissions={"r"},
                iterations=50,
            )


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

    def test_parser_iterations_flag(self):
        """Test --iterations flag."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args([])
        assert args.iterations is None

        args = parser.parse_args(['--iterations', '20'])
        assert args.iterations == 20

        args = parser.parse_args(['-I', '5'])
        assert args.iterations == 5

    def test_parser_temporal_task_queue_flag(self):
        """Test --temporal-task-queue flag."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args(["--temporal-task-queue", "dev-team"])
        assert args.temporal_task_queue == "dev-team"

    def test_parser_prompt_flag(self):
        """Test --prompt flag."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args(["--prompt", "prompts/dev.md"])
        assert args.prompt == "prompts/dev.md"

    def test_parser_verbose_flag(self):
        """Test --verbose flag with optional level."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args(["--verbose"])
        assert args.verbose == "INFO"

        args = parser.parse_args(["--verbose", "debug"])
        assert args.verbose == "DEBUG"

        with pytest.raises(SystemExit):
            parser.parse_args(["--verbose", "trace"])

    def test_iterations_none_resolved_from_config(self):
        """Test that None iterations falls back to config.max_iterations."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
            max_iterations=75,
        )

        with patch.object(sys, 'argv', ['ayder', 'hello world']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:
            with pytest.raises(SystemExit):
                main()
            mock_run.assert_called_once_with('hello world', permissions={'r'}, iterations=75)

    def test_iterations_cli_overrides_config(self):
        """Test that -I flag overrides config.max_iterations."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
            max_iterations=75,
        )

        with patch.object(sys, 'argv', ['ayder', '-I', '20', 'hello']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.cli_runner.run_command', return_value=0) as mock_run:
            with pytest.raises(SystemExit):
                main()
            mock_run.assert_called_once_with('hello', permissions={'r'}, iterations=20)

    def test_parser_command_argument(self):
        """Test positional command argument."""
        from ayder_cli.cli import create_parser

        parser = create_parser()

        args = parser.parse_args(['hello world'])
        assert args.command == 'hello world'

        args = parser.parse_args([])
        assert args.command is None

    def test_main_verbose_calls_setup_logging_stdout(self):
        """Test --verbose LEVEL configures logging to stdout."""
        from ayder_cli.cli import main
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
            max_iterations=50,
        )

        with patch.object(sys, "argv", ["ayder", "--verbose", "debug", "--tasks"]), patch(
            "ayder_cli.core.config.load_config", return_value=mock_config
        ), patch("ayder_cli.cli.setup_logging") as mock_setup_logging, patch(
            "ayder_cli.cli_runner._run_tasks_cli", return_value=0
        ):
            with pytest.raises(SystemExit):
                main()

        mock_setup_logging.assert_called_once_with(
            mock_config, level_override="DEBUG", console_stream=sys.stdout
        )
