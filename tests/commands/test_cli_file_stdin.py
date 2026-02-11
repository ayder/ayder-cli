"""Tests for CLI file and stdin input handling."""

import sys
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from ayder_cli.cli import main, read_input
from ayder_cli.cli_runner import run_command


class TestReadInput:
    """Test read_input function logic."""

    def test_read_input_from_file(self, tmp_path):
        """Test reading input from a file."""
        test_file = tmp_path / "prompt.txt"
        test_file.write_text("Hello from file")
        
        args = MagicMock()
        args.file = str(test_file)
        args.stdin = False
        args.command = None
        
        result = read_input(args)
        assert result == "Hello from file"

    def test_read_input_from_file_with_command(self, tmp_path):
        """Test reading input from file combined with command arg."""
        test_file = tmp_path / "context.txt"
        test_file.write_text("Some context")
        
        args = MagicMock()
        args.file = str(test_file)
        args.stdin = False
        args.command = "Explain this"
        
        result = read_input(args)
        assert "Context:\nSome context" in result
        assert "Question: Explain this" in result

    def test_read_input_from_stdin(self):
        """Test reading input from stdin."""
        args = MagicMock()
        args.file = None
        args.stdin = True
        args.command = None
        
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "Hello from pipe"
            
            result = read_input(args)
            assert result == "Hello from pipe"

    def test_read_input_command_only(self):
        """Test reading input from command argument only."""
        args = MagicMock()
        args.file = None
        args.stdin = False
        args.command = "Hello command"
        
        result = read_input(args)
        assert result == "Hello command"

    def test_read_input_none(self):
        """Test no input provided."""
        args = MagicMock()
        args.file = None
        args.stdin = False
        args.command = None
        
        result = read_input(args)
        assert result is None


class TestRunCommand:
    """Test run_command function."""

    def test_run_command_success(self):
        """Test successful command execution."""
        from ayder_cli.core.config import Config
    
        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
    
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "Response"}
        ]
    
        mock_agent = MagicMock()
        mock_registry = MagicMock()
    
        with patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry), \
             patch('openai.OpenAI'), \
             patch('builtins.print') as mock_print:
            from ayder_cli.cli_runner import run_command
            exit_code = run_command("test command")
            assert exit_code == 0

    def test_run_command_error(self):
        """Test error handling in command execution."""
        with patch('ayder_cli.core.config.load_config', side_effect=Exception("Config error")), \
             patch('builtins.print'):
            from ayder_cli.cli_runner import run_command
            exit_code = run_command("test")
            assert exit_code == 1

    def test_run_command_sets_project_context(self):
        """Test that run_command() initializes ProjectContext correctly."""
        from ayder_cli.core.config import Config
    
        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
    
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "Response"}
        ]
    
        mock_agent = MagicMock()
        mock_registry = MagicMock()
    
        with patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.core.context.ProjectContext') as mock_project_ctx_class, \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=mock_registry) as mock_create_registry, \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            
            from ayder_cli.cli_runner import run_command
            run_command("test")
            
            # Verify ProjectContext was initialized
            mock_project_ctx_class.assert_called_with(".")
            # Verify registry created with context
            mock_create_registry.assert_called()


class TestEdgeCases:
    """Test edge cases for file/stdin handling."""

    def test_file_not_found(self, tmp_path):
        """Test handling of non-existent file."""
        args = MagicMock()
        args.file = str(tmp_path / "nonexistent.txt")
        args.stdin = False
        args.command = None
        
        with patch('sys.exit') as mock_exit, \
             patch('sys.stderr.write'):
            read_input(args)
            mock_exit.assert_called_with(1)

    def test_file_read_error(self, tmp_path):
        """Test handling of file read errors."""
        test_file = tmp_path / "locked.txt"
        test_file.write_text("content")
        
        args = MagicMock()
        args.file = str(test_file)
        args.stdin = False
        args.command = None
        
        # Mock Path.read_text to raise PermissionError
        with patch('pathlib.Path.read_text', side_effect=PermissionError("Denied")), \
             patch('sys.exit') as mock_exit, \
             patch('sys.stderr.write'):
            read_input(args)
            mock_exit.assert_called_with(1)

    def test_stdin_without_pipe_error(self):
        """Test error when --stdin used without piped input."""
        args = MagicMock()
        args.file = None
        args.stdin = True
        args.command = None
        
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.exit') as mock_exit, \
             patch('sys.stderr.write'):
            mock_stdin.isatty.return_value = True  # Simulate TTY (interactive)
            
            read_input(args)
            mock_exit.assert_called_with(1)


class TestPipedInputAutoDetection:
    """Test auto-detection of piped input."""

    def test_piped_input_auto_enables_stdin(self):
        """Test that piped input automatically enables stdin mode."""
        from ayder_cli.core.config import Config
    
        mock_config = Config(num_ctx=4096, verbose=False)
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
    
        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="piped content"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=MagicMock()), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_piped_input_with_command_auto_enables_stdin(self):
        """Test that piped input with command automatically enables stdin mode."""
        from ayder_cli.core.config import Config
    
        mock_config = Config(num_ctx=4096, verbose=False)
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
    
        with patch.object(sys, 'argv', ['ayder', 'explain this']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="code to explain"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=MagicMock()), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_no_auto_detect_when_stdin_flag_explicit(self):
        """Test that explicit --stdin flag is not affected by auto-detection."""
        from ayder_cli.core.config import Config
    
        mock_config = Config(num_ctx=4096, verbose=False)
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
    
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="explicit stdin"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=MagicMock()), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_no_auto_detect_when_file_flag_used(self, tmp_path):
        """Test that --file flag prevents auto-detection even with piped stdin."""
        from ayder_cli.core.config import Config
    
        test_file = tmp_path / "test.txt"
        test_file.write_text("file content")
    
        mock_config = Config(num_ctx=4096, verbose=False)
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
    
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="piped content (should be ignored)"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.core.config.load_config', return_value=mock_config), \
             patch('ayder_cli.tools.registry.create_default_registry', return_value=MagicMock()), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0