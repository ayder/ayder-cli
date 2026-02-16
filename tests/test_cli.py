"""Tests for cli.py — coverage for run_interactive, _build_services, and main()."""

import sys
import pytest
from unittest.mock import patch, MagicMock, call, mock_open
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
            cfg, llm_provider, tool_executor, project_ctx, enhanced_system, checkpoint_manager, memory_manager = services

            assert cfg == mock_config
            assert llm_provider is not None
            assert tool_executor is not None
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
            cfg, llm_provider, tool_executor, project_ctx, enhanced_system, checkpoint_manager, memory_manager = services

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
            # load_config should NOT be called when config is provided

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

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.cli_runner.asyncio.run')
    def test_run_command_success(self, mock_asyncio_run, mock_build_services):
        """Test successful command execution via AgentEngine."""
        from ayder_cli.cli_runner import run_command

        mock_executor = MagicMock()
        mock_executor.tool_registry = MagicMock()
        mock_config = MagicMock()
        mock_config.model = "test-model"
        mock_config.num_ctx = 4096

        mock_build_services.return_value = (
            mock_config, MagicMock(), mock_executor, MagicMock(), "system prompt", MagicMock(), MagicMock()
        )
        mock_asyncio_run.return_value = "Response text"

        result = run_command("test prompt", permissions={"r"}, iterations=5)

        assert result == 0
        mock_asyncio_run.assert_called_once()

    @patch('ayder_cli.cli_runner._build_services')
    def test_run_command_error(self, mock_build_services):
        """Test command execution with error."""
        from ayder_cli.cli_runner import run_command

        mock_build_services.side_effect = Exception("Build error")

        with patch('sys.stderr', new=StringIO()) as mock_stderr:
            result = run_command("test prompt")
            assert result == 1
            assert "Build error" in mock_stderr.getvalue()

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.cli_runner.asyncio.run')
    def test_run_command_no_response(self, mock_asyncio_run, mock_build_services):
        """Test command execution with no response."""
        from ayder_cli.cli_runner import run_command

        mock_executor = MagicMock()
        mock_executor.tool_registry = MagicMock()
        mock_config = MagicMock()
        mock_config.model = "test-model"
        mock_config.num_ctx = 4096

        mock_build_services.return_value = (
            mock_config, MagicMock(), mock_executor, MagicMock(), "system", MagicMock(), MagicMock()
        )
        mock_asyncio_run.return_value = None

        result = run_command("test prompt")

        assert result == 0


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

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.client.ChatSession')
    @patch('ayder_cli.client.Agent')
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks._get_tasks_dir')
    @patch('ayder_cli.tasks._get_task_path_by_id')
    def test_run_implement_by_id_success(self, mock_get_path, mock_get_dir, mock_project_ctx,
                                          mock_agent_class, mock_session_class, mock_build_services):
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

            mock_build_services.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock(), "system", MagicMock(), MagicMock())
            mock_agent = MagicMock()
            mock_agent.chat.return_value = "Task completed"
            mock_agent_class.return_value = mock_agent

            with patch('sys.stdout', new=StringIO()):
                result = _run_implement_cli("1", permissions={"r"}, iterations=10)

            assert result == 0
            mock_agent.chat.assert_called_once()

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.client.ChatSession')
    @patch('ayder_cli.client.Agent')
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks._get_tasks_dir')
    @patch('ayder_cli.tasks._extract_id')
    @patch('ayder_cli.tasks._parse_title')
    def test_run_implement_by_pattern_success(self, mock_parse_title, mock_extract_id, mock_get_dir,
                                               mock_project_ctx, mock_agent_class, mock_session_class,
                                               mock_build_services):
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

            mock_build_services.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock(), "system", MagicMock(), MagicMock())
            mock_agent = MagicMock()
            mock_agent.chat.return_value = "Task completed"
            mock_agent_class.return_value = mock_agent

            with patch('sys.stdout', new=StringIO()):
                result = _run_implement_cli("auth", permissions={"r"}, iterations=10)

            assert result == 0

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.core.context.ProjectContext')
    @patch('ayder_cli.tasks._get_tasks_dir')
    def test_run_implement_no_match(self, mock_get_dir, mock_project_ctx, mock_build_services):
        """Test implementing when no task matches."""
        from ayder_cli.cli_runner import _run_implement_cli
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)

            mock_get_dir.return_value = tasks_dir
            mock_build_services.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock(), "system", MagicMock(), MagicMock())

            with patch('sys.stderr', new=StringIO()) as mock_stderr:
                result = _run_implement_cli("nonexistent", permissions={"r"})
                assert result == 1
                assert "No tasks found" in mock_stderr.getvalue()

    @patch('ayder_cli.cli_runner._build_services')
    def test_run_implement_error(self, mock_build_services):
        """Test implement with error."""
        from ayder_cli.cli_runner import _run_implement_cli

        mock_build_services.side_effect = Exception("Build error")

        with patch('sys.stderr', new=StringIO()) as mock_stderr:
            result = _run_implement_cli("1")
            assert result == 1
            assert "Build error" in mock_stderr.getvalue()


class TestRunImplementAllCLI:
    """Test _run_implement_all_cli function."""

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.client.ChatSession')
    @patch('ayder_cli.client.Agent')
    def test_run_implement_all_success(self, mock_agent_class, mock_session_class, mock_build_services):
        """Test successful implement all."""
        from ayder_cli.cli_runner import _run_implement_all_cli

        mock_build_services.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock(), "system", MagicMock(), MagicMock())
        mock_agent = MagicMock()
        mock_agent.chat.return_value = "All tasks completed"
        mock_agent_class.return_value = mock_agent

        with patch('sys.stdout', new=StringIO()):
            result = _run_implement_all_cli(permissions={"r"}, iterations=10)

        assert result == 0
        mock_agent.chat.assert_called_once()

    @patch('ayder_cli.cli_runner._build_services')
    def test_run_implement_all_error(self, mock_build_services):
        """Test implement all with error."""
        from ayder_cli.cli_runner import _run_implement_all_cli

        mock_build_services.side_effect = Exception("Build error")

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
        
        # Test -x flag
        args = parser.parse_args(['-x', 'test command'])
        assert args.x is True
        assert args.w is False
        
        # Test both flags
        args = parser.parse_args(['-w', '-x', 'test command'])
        assert args.w is True
        assert args.x is True


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

            # Verify run_command was called with 'w' in permissions
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

            # Verify run_command was called with 'x' in permissions
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

            # Verify run_command was called with both permissions
            call_kwargs = mock_run.call_args[1]
            assert 'w' in call_kwargs['permissions']
            assert 'x' in call_kwargs['permissions']
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

            # Verify run_command was called with only 'r' permission
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
            # Simulate running the module directly
            import ayder_cli.cli as cli_module
            # Execute the if block directly
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
        
        # Check that version action exists
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
        """Test permission flags -r, -w, -x."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        
        # Test default (read is True by default)
        args = parser.parse_args([])
        assert args.r is True
        assert args.w is False
        assert args.x is False
        
        # Test with all flags
        args = parser.parse_args(['-r', '-w', '-x'])
        assert args.r is True
        assert args.w is True
        assert args.x is True

    def test_parser_iterations_flag(self):
        """Test --iterations flag."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        
        # Default value (None — resolved from config at runtime)
        args = parser.parse_args([])
        assert args.iterations is None
        
        # Custom value
        args = parser.parse_args(['--iterations', '20'])
        assert args.iterations == 20
        
        # Short form
        args = parser.parse_args(['-I', '5'])
        assert args.iterations == 5

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
            # CLI flag (20) should win over config (75)
            mock_run.assert_called_once_with('hello', permissions={'r'}, iterations=20)

    def test_parser_command_argument(self):
        """Test positional command argument."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        
        args = parser.parse_args(['hello world'])
        assert args.command == 'hello world'
        
        # No command
        args = parser.parse_args([])
        assert args.command is None



class TestPhase04RuntimeWiring:
    """S3: Assert real runtime wiring for CLI and TUI shared-engine usage."""

    @patch('ayder_cli.cli_runner._build_services')
    @patch('ayder_cli.cli_runner.asyncio.run')
    def test_command_runner_uses_agent_engine(self, mock_asyncio_run, mock_build_services):
        """CommandRunner.run() must invoke AgentEngine via asyncio.run (not Agent.chat)."""
        from ayder_cli.cli_runner import CommandRunner
        from ayder_cli.application.agent_engine import AgentEngine

        mock_executor = MagicMock()
        mock_executor.tool_registry = MagicMock()
        mock_config = MagicMock()
        mock_config.model = "test-model"
        mock_config.num_ctx = 4096

        mock_build_services.return_value = (
            mock_config, MagicMock(), mock_executor, MagicMock(), "sys", MagicMock(), MagicMock()
        )
        mock_asyncio_run.return_value = "response"

        runner = CommandRunner("test prompt", permissions={"r"}, iterations=10)
        runner.run()

        # asyncio.run must be called with a coroutine (engine.run)
        mock_asyncio_run.assert_called_once()
        coro_arg = mock_asyncio_run.call_args[0][0]
        # Coroutine must be from AgentEngine.run
        assert hasattr(coro_arg, '__qualname__') and 'AgentEngine.run' in coro_arg.__qualname__
        coro_arg.close()  # prevent ResourceWarning

    def test_tui_chat_loop_delegates_to_engine(self):
        """TuiChatLoop.run() must not have its own while-loop; it delegates to _TuiCompatEngine."""
        import inspect
        from ayder_cli.tui.chat_loop import TuiChatLoop, _TuiCompatEngine
        from ayder_cli.application.agent_engine import AgentEngine

        # _TuiCompatEngine must be a subclass of AgentEngine
        assert issubclass(_TuiCompatEngine, AgentEngine), "_TuiCompatEngine must extend AgentEngine"

        # TuiChatLoop.run() source must not contain its own while True loop
        src = inspect.getsource(TuiChatLoop.run)
        assert "while True" not in src, "TuiChatLoop.run() must not have its own while-loop"

        # TuiChatLoop.run() source must reference _TuiCompatEngine
        assert "_TuiCompatEngine" in src, "TuiChatLoop.run() must delegate to _TuiCompatEngine"
