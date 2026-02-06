"""Tests for file and stdin input in CLI."""
import sys
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import pytest


class TestReadInput:
    """Tests for read_input() function."""
    
    def test_read_input_from_file(self, tmp_path):
        """Test reading prompt from file."""
        # Create a temporary file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content from file")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == "Test content from file"
    
    def test_read_input_file_not_found(self):
        """Test that FileNotFoundError exits with code 1."""
        with patch.object(sys, 'argv', ['ayder', '-f', 'nonexistent.txt']):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            with pytest.raises(SystemExit) as exc_info:
                read_input(args)
            assert exc_info.value.code == 1
    
    def test_read_input_from_stdin(self):
        """Test reading prompt from stdin."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "Content from stdin"
        
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys, 'stdin', mock_stdin):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == "Content from stdin"
    
    def test_read_input_stdin_no_pipe(self):
        """Test that --stdin without pipe exits with code 1."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True  # No pipe
        
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys, 'stdin', mock_stdin):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            with pytest.raises(SystemExit) as exc_info:
                read_input(args)
            assert exc_info.value.code == 1
    
    def test_read_input_file_with_command(self, tmp_path):
        """Test combining file content with command."""
        test_file = tmp_path / "context.txt"
        test_file.write_text("File context")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file), 'explain this']):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            expected = "Context:\nFile context\n\nQuestion: explain this"
            assert result == expected
    
    def test_read_input_stdin_with_command(self):
        """Test combining stdin content with command."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "Stdin context"
        
        with patch.object(sys, 'argv', ['ayder', '--stdin', 'review this']), \
             patch.object(sys, 'stdin', mock_stdin):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            expected = "Context:\nStdin context\n\nQuestion: review this"
            assert result == expected
    
    def test_read_input_command_only(self):
        """Test command without file or stdin."""
        with patch.object(sys, 'argv', ['ayder', 'just a command']):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == "just a command"
    
    def test_read_input_no_input(self):
        """Test with no input provided."""
        with patch.object(sys, 'argv', ['ayder']):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result is None


class TestRunCommand:
    """Tests for run_command() function."""
    
    def test_run_command_success(self):
        """Test successful command execution."""
        from ayder_cli.config import Config
        
        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model"
        )
        
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "Response"}
        ]
        
        mock_agent = MagicMock()
        
        with patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print') as mock_print:
            from ayder_cli.cli import run_command
            exit_code = run_command("test command")
            assert exit_code == 0
            mock_print.assert_called_with("Response")
    
    def test_run_command_error(self):
        """Test command execution with error."""
        with patch('ayder_cli.config.load_config', side_effect=Exception("Test error")):
            from ayder_cli.cli import run_command
            exit_code = run_command("test command")
            assert exit_code == 1

    def test_run_command_sets_project_context(self):
        """Test that run_command() calls set_project_context_for_modules() for path sandboxing.
        
        This is a security fix (FIX-001) - command mode must set ProjectContext before
        any tool execution to ensure proper path sandboxing, matching interactive mode behavior.
        """
        from ayder_cli.config import Config
        
        mock_config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="test-model"
        )
        
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "Response"}
        ]
        
        mock_agent = MagicMock()
        mock_project_ctx = MagicMock()
        
        with patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=mock_agent), \
             patch('ayder_cli.client.set_project_context_for_modules') as mock_set_ctx, \
             patch('ayder_cli.path_context.ProjectContext') as mock_project_ctx_class, \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            mock_project_ctx_class.return_value = mock_project_ctx
            from ayder_cli.cli import run_command
            exit_code = run_command("test command")
            assert exit_code == 0
            # Verify ProjectContext was created with current directory
            mock_project_ctx_class.assert_called_once_with(".")
            # Verify set_project_context_for_modules was called before any tool execution
            mock_set_ctx.assert_called_once_with(mock_project_ctx)


class TestMainIntegration:
    """Integration tests for main() with file/stdin."""
    
    def test_main_with_file_calls_run_command(self, tmp_path):
        """Test that main() with --file calls run_command()."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]), \
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run_cmd:
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            mock_run_cmd.assert_called_once_with("Test content", permissions={"r"}, iterations=10)

    def test_main_with_stdin_calls_run_command(self):
        """Test that main() with --stdin calls run_command()."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "Stdin content"
        
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys, 'stdin', mock_stdin), \
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run_cmd:
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            mock_run_cmd.assert_called_once_with("Stdin content", permissions={"r"}, iterations=10)

    def test_main_with_command_calls_run_command(self):
        """Test that main() with command calls run_command()."""
        with patch.object(sys, 'argv', ['ayder', 'test command']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run_cmd:
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            mock_run_cmd.assert_called_once_with("test command", permissions={"r"}, iterations=10)

    def test_main_no_input_calls_run_chat(self):
        """Test that main() without input calls run_chat()."""
        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.client.run_chat') as mock_run_chat:
            from ayder_cli.cli import main
            main()
            mock_run_chat.assert_called_once_with(permissions={"r"}, iterations=10)
    
    def test_main_file_with_command_combines(self, tmp_path):
        """Test that main() combines file and command."""
        test_file = tmp_path / "context.txt"
        test_file.write_text("Context")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file), 'question']), \
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run_cmd:
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            expected = "Context:\nContext\n\nQuestion: question"
            mock_run_cmd.assert_called_once_with(expected, permissions={"r"}, iterations=10)

    def test_main_stdin_with_command_combines(self):
        """Test that main() combines stdin and command."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "Stdin data"
        
        with patch.object(sys, 'argv', ['ayder', '--stdin', 'analyze']), \
             patch.object(sys, 'stdin', mock_stdin), \
             patch('ayder_cli.cli.run_command', return_value=0) as mock_run_cmd:
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            expected = "Context:\nStdin data\n\nQuestion: analyze"
            mock_run_cmd.assert_called_once_with(expected, permissions={"r"}, iterations=10)


class TestMutualExclusivity:
    """Tests for mutually exclusive file and stdin flags."""
    
    def test_file_and_stdin_mutually_exclusive(self):
        """Test that --file and --stdin cannot be used together."""
        with patch.object(sys, 'argv', ['ayder', '--file', 'test.txt', '--stdin']):
            from ayder_cli.cli import create_parser
            parser = create_parser()
            with pytest.raises(SystemExit) as exc_info:
                parser.parse_args()
            assert exc_info.value.code == 2  # argparse error


class TestEdgeCases:
    """Edge case tests for file/stdin input."""
    
    def test_empty_file(self, tmp_path):
        """Test reading an empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == ""
    
    def test_empty_stdin(self):
        """Test reading empty stdin."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = ""
        
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys, 'stdin', mock_stdin):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == ""
    
    def test_multiline_file_content(self, tmp_path):
        """Test reading multiline file content."""
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3")
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            result = read_input(args)
            assert result == "Line 1\nLine 2\nLine 3"
    
    def test_file_read_error(self):
        """Test handling generic file read errors."""
        with patch.object(sys, 'argv', ['ayder', '-f', 'test.txt']), \
             patch('pathlib.Path.read_text', side_effect=PermissionError("No permission")):
            from ayder_cli.cli import create_parser, read_input
            parser = create_parser()
            args = parser.parse_args()
            with pytest.raises(SystemExit) as exc_info:
                read_input(args)
            assert exc_info.value.code == 1


class TestPipedInputAutoDetection:
    """Tests for automatic piped input detection."""
    
    def test_piped_input_auto_enables_stdin(self):
        """Test that piped input automatically enables stdin mode."""
        from ayder_cli.config import Config
        
        mock_config = Config()
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
        
        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="piped content"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_piped_input_with_command_auto_enables_stdin(self):
        """Test that piped input with command automatically enables stdin mode."""
        from ayder_cli.config import Config
        
        mock_config = Config()
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
        
        with patch.object(sys, 'argv', ['ayder', 'explain this']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="code to explain"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_no_auto_detect_when_stdin_flag_explicit(self):
        """Test that explicit --stdin flag is not affected by auto-detection."""
        from ayder_cli.config import Config
        
        mock_config = Config()
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
        
        with patch.object(sys, 'argv', ['ayder', '--stdin']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="explicit stdin"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_no_auto_detect_when_file_flag_used(self, tmp_path):
        """Test that --file flag prevents auto-detection even with piped stdin."""
        from ayder_cli.config import Config
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("file content")
        
        mock_config = Config()
        mock_session = MagicMock()
        mock_session.get_messages.return_value = [
            {"role": "assistant", "content": "Response"}
        ]
        
        with patch.object(sys, 'argv', ['ayder', '-f', str(test_file)]), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch.object(sys.stdin, 'read', return_value="piped content (should be ignored)"), \
             patch('ayder_cli.client.ChatSession', return_value=mock_session), \
             patch('ayder_cli.client.Agent', return_value=MagicMock()), \
             patch('ayder_cli.config.load_config', return_value=mock_config), \
             patch('openai.OpenAI'), \
             patch('builtins.print'):
            from ayder_cli.cli import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_no_auto_detect_when_tui_flag_used(self):
        """Test that --tui flag prevents auto-detection."""
        with patch.object(sys, 'argv', ['ayder', '--tui']), \
             patch.object(sys.stdin, 'isatty', return_value=False), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            from ayder_cli.cli import main
            main()
            mock_run_tui.assert_called_once()
    
    def test_no_auto_detect_when_tty(self):
        """Test that auto-detection does NOT trigger when stdin is a TTY."""
        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.client.run_chat') as mock_run_chat:
            from ayder_cli.cli import main
            main()
            mock_run_chat.assert_called_once()
