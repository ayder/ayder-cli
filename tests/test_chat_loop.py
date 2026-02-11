"""Tests for chat_loop.py module."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import field

from ayder_cli.chat_loop import (
    LoopState,
    LoopConfig,
    IterationController,
    ToolCallHandler,
    ChatLoop,
)
from ayder_cli.checkpoint_manager import CheckpointManager as CheckpointManagerClass
from ayder_cli.memory import MemoryManager
from ayder_cli.core.context import ProjectContext


class TestLoopState:
    """Test LoopState dataclass."""

    def test_default_values(self):
        """Test LoopState default values."""
        state = LoopState()
        assert state.iteration == 0
        assert state.should_continue is True
        assert state.result is None

    def test_custom_values(self):
        """Test LoopState with custom values."""
        state = LoopState(iteration=5, should_continue=False, result="test")
        assert state.iteration == 5
        assert state.should_continue is False
        assert state.result == "test"


class TestLoopConfig:
    """Test LoopConfig dataclass."""

    def test_default_values(self):
        """Test LoopConfig default values."""
        config = LoopConfig()
        assert config.max_iterations == 50
        assert config.model == "qwen3-coder:latest"
        assert config.num_ctx == 65536
        assert config.verbose is False
        assert config.permissions == set()

    def test_custom_values(self):
        """Test LoopConfig with custom values."""
        config = LoopConfig(
            max_iterations=10,
            model="gpt-4",
            num_ctx=8192,
            verbose=True,
            permissions={"r", "w"}
        )
        assert config.max_iterations == 10
        assert config.model == "gpt-4"
        assert config.num_ctx == 8192
        assert config.verbose is True
        assert config.permissions == {"r", "w"}


class TestIterationController:
    """Test IterationController class."""

    def test_initialization(self):
        """Test IterationController initialization."""
        ctrl = IterationController(max_iterations=10)
        assert ctrl.max_iterations == 10
        assert ctrl.iteration == 0
        assert ctrl.cm is None

    def test_initialization_with_checkpoint_manager(self):
        """Test IterationController with checkpoint manager."""
        cm = CheckpointManagerClass(ProjectContext("."))
        ctrl = IterationController(max_iterations=10, checkpoint_manager=cm)
        assert ctrl.cm == cm

    def test_increment(self):
        """Test iteration increment."""
        ctrl = IterationController(max_iterations=10)
        assert ctrl.increment() == 1
        assert ctrl.increment() == 2
        assert ctrl.iteration == 2

    def test_reset(self):
        """Test iteration reset."""
        ctrl = IterationController(max_iterations=10)
        ctrl.increment()
        ctrl.increment()
        ctrl.reset()
        assert ctrl.iteration == 0

    def test_should_trigger_checkpoint_false(self):
        """Test checkpoint trigger when under limit."""
        ctrl = IterationController(max_iterations=5)
        ctrl.increment()
        ctrl.increment()
        assert ctrl.should_trigger_checkpoint() is False

    def test_should_trigger_checkpoint_true(self):
        """Test checkpoint trigger when over limit."""
        ctrl = IterationController(max_iterations=2)
        ctrl.increment()  # 1
        ctrl.increment()  # 2
        ctrl.increment()  # 3
        assert ctrl.should_trigger_checkpoint() is True

    def test_handle_checkpoint_no_checkpoint_manager(self):
        """Test handle_checkpoint returns False when no checkpoint manager."""
        ctrl = IterationController(max_iterations=10)
        result = ctrl.handle_checkpoint(lambda: None)
        assert result is False

    def test_handle_checkpoint_no_saved_memory(self):
        """Test handle_checkpoint returns False when no saved memory."""
        cm = CheckpointManagerClass(ProjectContext("."))
        ctrl = IterationController(max_iterations=10, checkpoint_manager=cm)
        result = ctrl.handle_checkpoint(lambda: None)
        assert result is False

    def test_handle_checkpoint_success(self, tmp_path):
        """Test handle_checkpoint success case."""
        project_ctx = ProjectContext(str(tmp_path))
        cm = CheckpointManagerClass(project_ctx)
        cm._ensure_checkpoint_dir()
        cm._checkpoint_file.write_text("test memory", encoding="utf-8")
        
        ctrl = IterationController(max_iterations=10, checkpoint_manager=cm)
        ctrl.increment()
        ctrl.increment()
        
        restore_called = False
        def restore_fn():
            nonlocal restore_called
            restore_called = True
        
        result = ctrl.handle_checkpoint(restore_fn)
        
        assert result is True
        assert restore_called is True
        assert ctrl.iteration == 0  # Should be reset


class TestToolCallHandler:
    """Test ToolCallHandler class."""

    def test_initialization(self):
        """Test ToolCallHandler initialization."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, {"r"}, True)
        
        assert handler.tool_executor == executor
        assert handler.session == session
        assert handler.permissions == {"r"}
        assert handler.verbose is True

    def test_parse_tool_calls_with_tool_calls(self):
        """Test parsing when LLM returns tool_calls."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, set(), False)
        
        mock_tool_call = Mock()
        msg = Mock()
        msg.tool_calls = [mock_tool_call]
        
        tool_calls, custom_calls = handler.parse_tool_calls(msg, "some content")
        
        assert tool_calls == [mock_tool_call]
        assert custom_calls == []

    def test_parse_tool_calls_no_tools(self):
        """Test parsing when no tools are called."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, set(), False)
        
        msg = Mock()
        msg.tool_calls = None
        
        with patch("ayder_cli.chat_loop.parse_custom_tool_calls", return_value=[]):
            tool_calls, custom_calls = handler.parse_tool_calls(msg, "just text")
        
        assert tool_calls is None
        assert custom_calls == []

    def test_parse_tool_calls_with_custom_calls(self):
        """Test parsing custom tool calls."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, set(), False)
        
        msg = Mock()
        msg.tool_calls = None
        custom_call = {"name": "test_tool", "arguments": {}}
        
        with patch("ayder_cli.chat_loop.parse_custom_tool_calls", return_value=[custom_call]):
            tool_calls, custom_calls = handler.parse_tool_calls(msg, "<function=test>")
        
        assert tool_calls is None
        assert custom_calls == [custom_call]

    def test_parse_tool_calls_with_parser_error(self):
        """Test parsing with parser error."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, set(), False)
        
        msg = Mock()
        msg.tool_calls = None
        error_call = {"error": "parse error"}
        
        with patch("ayder_cli.chat_loop.parse_custom_tool_calls", return_value=[error_call]):
            tool_calls, custom_calls = handler.parse_tool_calls(msg, "bad syntax")
        
        assert tool_calls is None
        assert custom_calls == []  # Should be cleared due to error
        session.add_message.assert_called_once()

    def test_execute_with_tool_calls(self):
        """Test executing tool calls."""
        session = Mock()
        executor = Mock()
        executor.execute_tool_calls.return_value = False  # Not terminal
        handler = ToolCallHandler(executor, session, {"r"}, False)
        
        msg = Mock()
        mock_tool_call = Mock()
        
        result = handler.execute(msg, [mock_tool_call], [])
        
        assert result is False  # Not terminal
        session.append_raw.assert_called_once_with(msg)
        executor.execute_tool_calls.assert_called_once()

    def test_execute_with_custom_calls(self):
        """Test executing custom tool calls."""
        session = Mock()
        executor = Mock()
        executor.execute_custom_calls.return_value = False
        handler = ToolCallHandler(executor, session, {"r"}, False)
        
        msg = Mock()
        custom_call = {"name": "test", "arguments": {}}
        
        result = handler.execute(msg, [], [custom_call])
        
        assert result is False
        session.append_raw.assert_called_once_with(msg)
        executor.execute_custom_calls.assert_called_once()

    def test_execute_terminal_tool(self):
        """Test terminal tool execution."""
        session = Mock()
        executor = Mock()
        executor.execute_tool_calls.return_value = True  # Terminal
        handler = ToolCallHandler(executor, session, {"r"}, False)
        
        msg = Mock()
        mock_tool_call = Mock()
        
        result = handler.execute(msg, [mock_tool_call], [])
        
        assert result is True  # Terminal

    def test_execute_no_tools(self):
        """Test execute with no tools."""
        session = Mock()
        executor = Mock()
        handler = ToolCallHandler(executor, session, {"r"}, False)
        
        msg = Mock()
        
        result = handler.execute(msg, [], [])
        
        assert result is False
        session.append_raw.assert_not_called()


class TestChatLoop:
    """Test ChatLoop class."""

    def test_initialization(self):
        """Test ChatLoop initialization."""
        llm = Mock()
        executor = Mock()
        session = Mock()
        config = LoopConfig()
        
        loop = ChatLoop(llm, executor, session, config)
        
        assert loop.llm == llm
        assert loop.tools == executor
        assert loop.session == session
        assert loop.config == config
        assert loop.iteration_ctrl is not None
        assert loop.tool_handler is not None
        assert loop.mm is None  # No memory manager by default

    def test_initialization_with_memory_manager(self):
        """Test ChatLoop initialization with memory manager."""
        llm = Mock()
        executor = Mock()
        session = Mock()
        config = LoopConfig()
        mm = Mock()
        cm = Mock()
        
        loop = ChatLoop(llm, executor, session, config, 
                       checkpoint_manager=cm, memory_manager=mm)
        
        assert loop.cm == cm
        assert loop.mm == mm

    def test_run_simple_text_response(self):
        """Test run with simple text response."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        mock_message = Mock()
        mock_message.content = "Hello there"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        llm.chat.return_value = mock_response
        
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = []
        
        config = LoopConfig()
        loop = ChatLoop(llm, executor, session, config)
        
        with patch("ayder_cli.chat_loop.parse_custom_tool_calls", return_value=[]):
            result = loop.run("test input")
        
        assert result == "Hello there"
        session.add_message.assert_any_call("user", "test input")
        session.add_message.assert_any_call("assistant", "Hello there")

    def test_run_with_tool_calls(self):
        """Test run with tool calls."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        llm.chat.return_value = mock_response
        
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = []
        executor.execute_tool_calls.return_value = False  # Not terminal
        
        config = LoopConfig(max_iterations=5)
        loop = ChatLoop(llm, executor, session, config)
        
        # Second call returns text response
        mock_message2 = Mock()
        mock_message2.content = "Done"
        mock_message2.tool_calls = None
        mock_choice2 = Mock()
        mock_choice2.message = mock_message2
        mock_response2 = Mock()
        mock_response2.choices = [mock_choice2]
        
        llm.chat.side_effect = [mock_response, mock_response2]
        
        with patch("ayder_cli.chat_loop.parse_custom_tool_calls", return_value=[]):
            result = loop.run("test")
        
        assert result == "Done"
        assert llm.chat.call_count == 2

    def test_run_terminal_tool(self):
        """Test run stops on terminal tool."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        llm.chat.return_value = mock_response
        
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = []
        executor.execute_tool_calls.return_value = True  # Terminal
        
        config = LoopConfig(max_iterations=10)
        loop = ChatLoop(llm, executor, session, config)
        
        result = loop.run("test")
        
        assert result is None
        assert llm.chat.call_count == 1  # Should stop after terminal tool

    def test_get_tool_schemas_no_tools(self):
        """Test _get_tool_schemas with no_tools flag."""
        llm = Mock()
        session = Mock()
        session.state = {"no_tools": True}
        executor = Mock()
        
        config = LoopConfig()
        loop = ChatLoop(llm, executor, session, config)
        
        schemas = loop._get_tool_schemas()
        
        assert schemas == []

    def test_get_tool_schemas_with_tools(self):
        """Test _get_tool_schemas normal case."""
        llm = Mock()
        session = Mock()
        session.state = {}
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = [{"type": "function"}]
        
        config = LoopConfig()
        loop = ChatLoop(llm, executor, session, config)
        
        schemas = loop._get_tool_schemas()
        
        assert schemas == [{"type": "function"}]

    def test_handle_checkpoint_with_memory_manager(self):
        """Test _handle_checkpoint with memory manager and existing checkpoint."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = []
        
        config = LoopConfig(max_iterations=5)
        
        mm = Mock()
        cm = Mock()
        cm.has_saved_checkpoint.return_value = True
        
        loop = ChatLoop(llm, executor, session, config,
                       checkpoint_manager=cm, memory_manager=mm)
        
        # Manually set iteration over limit
        loop.iteration_ctrl._iteration = 10
        
        result = loop._handle_checkpoint()
        
        assert result is True
        mm.restore_from_checkpoint.assert_called_once_with(session)

    def test_handle_checkpoint_creates_checkpoint(self):
        """Test _handle_checkpoint creates checkpoint when none exists."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        executor = Mock()
        executor.tool_registry = Mock()
        executor.tool_registry.get_schemas.return_value = []
        
        config = LoopConfig(max_iterations=5, model="test-model", num_ctx=4096)
        
        mm = Mock()
        mm.create_checkpoint.return_value = True
        cm = Mock()
        cm.has_saved_checkpoint.return_value = False
        
        loop = ChatLoop(llm, executor, session, config,
                       checkpoint_manager=cm, memory_manager=mm)
        
        # Manually set iteration over limit
        loop.iteration_ctrl._iteration = 10
        
        result = loop._handle_checkpoint()
        
        assert result is True
        mm.create_checkpoint.assert_called_once_with(
            session, "test-model", 4096, set(), False
        )

    def test_handle_checkpoint_no_memory_manager(self):
        """Test _handle_checkpoint returns False without memory manager."""
        llm = Mock()
        session = Mock()
        session.state = {}
        
        executor = Mock()
        
        config = LoopConfig()
        loop = ChatLoop(llm, executor, session, config)
        
        # Manually set iteration over limit
        loop.iteration_ctrl._iteration = 10
        
        result = loop._handle_checkpoint()
        
        assert result is False
