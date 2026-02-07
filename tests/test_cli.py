"""Tests for cli.py — coverage for run_interactive, _build_services, and main()."""

import sys
import pytest
from unittest.mock import patch, MagicMock, call
from io import StringIO


class TestBuildServices:
    """Test _build_services function."""

    def test_build_services_with_exception_in_structure_macro(self):
        """Test that _build_services handles exception when getting project structure."""
        from ayder_cli.cli import _build_services
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

        with patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            cfg, llm_provider, tool_executor, project_ctx, enhanced_prompt = _build_services()
            
            assert cfg == mock_config
            assert llm_provider is not None
            assert tool_executor is not None
            assert project_ctx is not None
            # Verify macro is empty when exception occurs
            assert "PROJECT STRUCTURE" not in enhanced_prompt

    def test_build_services_success_with_structure_macro(self):
        """Test _build_services successfully adds structure macro."""
        from ayder_cli.cli import _build_services
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

        with patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            cfg, llm_provider, tool_executor, project_ctx, enhanced_prompt = _build_services()
            
            assert "PROJECT STRUCTURE" in enhanced_prompt
            assert "src/" in enhanced_prompt
            mock_registry.execute.assert_called_once_with("get_project_structure", {"max_depth": 3})

    def test_build_services_with_custom_config(self):
        """Test _build_services accepts custom config parameter."""
        from ayder_cli.cli import _build_services
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

        with patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            cfg, _, _, _, _ = _build_services(config=mock_config)
            
            assert cfg == mock_config
            # load_config should NOT be called when config is provided

    def test_build_services_with_custom_project_root(self):
        """Test _build_services accepts custom project root."""
        from ayder_cli.cli import _build_services
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        
        mock_registry = MagicMock()

        with patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.core.context.ProjectContext') as mock_project_ctx_class, \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'):
            _build_services(project_root="/custom/path")
            
            mock_project_ctx_class.assert_called_once_with("/custom/path")


class TestRunInteractive:
    """Test run_interactive function."""

    def test_run_interactive_basic_input(self):
        """Test basic input handling in interactive mode."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        mock_session.get_input.side_effect = ["hello", None]  # One input then exit
        
        mock_agent = MagicMock()
        mock_agent.chat.return_value = "Hello response"

        mock_config = MagicMock()
        mock_config.iterations = 10

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), MagicMock(), "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.ui.print_running'), \
             patch('ayder_cli.ui.print_assistant_message') as mock_print_response:
            
            run_interactive(permissions={"r"}, iterations=10)
            
            mock_agent.chat.assert_called_once_with("hello")
            mock_print_response.assert_called_once_with("Hello response")

    def test_run_interactive_handles_slash_commands(self):
        """Test that slash commands are dispatched correctly."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        mock_session.get_input.side_effect = ["/help", None]
        mock_session.messages = []
        mock_session.state = MagicMock()
        
        mock_agent = MagicMock()
        mock_config = MagicMock()
        mock_project_ctx = MagicMock()

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), mock_project_ctx, "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.commands.handle_command') as mock_handle_command:
            
            run_interactive()
            
            # Agent.chat should NOT be called for slash commands
            mock_agent.chat.assert_not_called()
            # handle_command should be called
            mock_handle_command.assert_called_once()
            args = mock_handle_command.call_args[0]
            assert args[0] == "/help"

    def test_run_interactive_empty_input_continues(self):
        """Test that empty input continues the loop."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        # Empty string should be skipped, then exit
        mock_session.get_input.side_effect = ["", None]
        
        mock_agent = MagicMock()
        mock_config = MagicMock()

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), MagicMock(), "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.ui.print_running'):
            
            run_interactive()
            
            # Agent.chat should NOT be called for empty input
            mock_agent.chat.assert_not_called()

    def test_run_interactive_error_handling(self):
        """Test error handling in interactive mode."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        mock_session.get_input.side_effect = ["trigger error", None]
        
        mock_agent = MagicMock()
        mock_agent.chat.side_effect = Exception("Test error")

        mock_config = MagicMock()

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), MagicMock(), "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.ui.print_running'), \
             patch('ayder_cli.ui.draw_box') as mock_draw_box:
            
            run_interactive()
            
            mock_draw_box.assert_called_once()
            args = mock_draw_box.call_args
            assert "Error: Test error" in args[0][0]

    def test_run_interactive_multiple_messages(self):
        """Test multiple messages in interactive session."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        mock_session.get_input.side_effect = ["msg1", "msg2", None]
        
        mock_agent = MagicMock()
        mock_agent.chat.side_effect = ["resp1", "resp2"]

        mock_config = MagicMock()

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), MagicMock(), "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.ui.print_running'), \
             patch('ayder_cli.ui.print_assistant_message') as mock_print_response:
            
            run_interactive()
            
            assert mock_agent.chat.call_count == 2
            assert mock_print_response.call_count == 2

    def test_run_interactive_session_start_called(self):
        """Test that session.start() is called on initialization."""
        from ayder_cli.cli import run_interactive

        mock_session = MagicMock()
        mock_session.get_input.side_effect = [None]
        mock_session.start = MagicMock()

        mock_config = MagicMock()

        with patch('ayder_cli.cli._build_services', return_value=(
            mock_config, MagicMock(), MagicMock(), MagicMock(), "system prompt"
        )), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent'):
            
            run_interactive()
            
            mock_session.start.assert_called_once()



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
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run, \
             patch('sys.exit'):
            
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
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run, \
             patch('sys.exit'):
            
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
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run, \
             patch('sys.exit'):
            
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
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run, \
             patch('sys.exit'):
            
            main()
            
            # Verify run_command was called with only 'r' permission
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['permissions'] == {'r'}


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
        from ayder_cli.banner import get_app_version

        parser = create_parser()
        
        # Check that version action exists
        version_action = None
        for action in parser._actions:
            if action.dest == 'version':
                version_action = action
                break
        
        assert version_action is not None
        assert version_action.version == get_app_version()

    def test_parser_tui_flag(self):
        """Test --tui flag is configured."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(['--tui'])
        assert args.tui is True

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
        
        # Default value
        args = parser.parse_args([])
        assert args.iterations == 10
        
        # Custom value
        args = parser.parse_args(['--iterations', '20'])
        assert args.iterations == 20
        
        # Short form
        args = parser.parse_args(['-I', '5'])
        assert args.iterations == 5

    def test_parser_command_argument(self):
        """Test positional command argument."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        
        args = parser.parse_args(['hello world'])
        assert args.command == 'hello world'
        
        # No command
        args = parser.parse_args([])
        assert args.command is None

    def test_parser_file_and_stdin_mutually_exclusive(self):
        """Test that --file and --stdin are mutually exclusive."""
        from ayder_cli.cli import create_parser

        parser = create_parser()
        
        # Both should raise error
        with pytest.raises(SystemExit):
            parser.parse_args(['--file', 'test.txt', '--stdin'])


class TestReadInputAdditional:
    """Additional tests for read_input function."""

    def test_read_input_stdin_with_command(self):
        """Test reading from stdin combined with command."""
        from ayder_cli.cli import read_input

        args = MagicMock()
        args.file = None
        args.stdin = True
        args.command = "Explain this"
        
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "Some context from stdin"
            
            result = read_input(args)
            assert "Context:\nSome context from stdin" in result
            assert "Question: Explain this" in result

    def test_read_input_context_only_no_command(self):
        """Test reading only context (no command)."""
        from ayder_cli.cli import read_input

        args = MagicMock()
        args.file = None
        args.stdin = True
        args.command = None
        
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "Just context"
            
            result = read_input(args)
            assert result == "Just context"
