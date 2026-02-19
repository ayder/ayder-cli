"""Tests for memory management."""

import json
import pytest
from unittest.mock import Mock

from ayder_cli.memory import save_memory, load_memory, MemoryManager, create_memory_manager
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestSaveMemory:
    """Test save_memory() function."""

    def test_save_basic_memory(self, tmp_path, project_context):
        """Test saving a basic memory."""
        result = save_memory(project_context, "The API uses JWT tokens")

        assert isinstance(result, ToolSuccess)
        assert "Memory saved" in result

        memory_file = tmp_path / ".ayder" / "memory" / "memories.jsonl"
        assert memory_file.exists()

        lines = memory_file.read_text().strip().split('\n')
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["content"] == "The API uses JWT tokens"
        assert "id" in entry
        assert "timestamp" in entry

    def test_save_memory_with_category(self, tmp_path, project_context):
        """Test saving memory with category."""
        result = save_memory(project_context, "Use PostgreSQL", category="architecture")

        assert isinstance(result, ToolSuccess)

        memory_file = tmp_path / ".ayder" / "memory" / "memories.jsonl"
        entry = json.loads(memory_file.read_text().strip())
        assert entry["category"] == "architecture"

    def test_save_memory_with_tags(self, tmp_path, project_context):
        """Test saving memory with tags."""
        result = save_memory(project_context, "Content", tags="db,backend")
        assert isinstance(result, ToolSuccess)

        memory_file = tmp_path / ".ayder" / "memory" / "memories.jsonl"
        entry = json.loads(memory_file.read_text().strip())
        assert entry["tags"] == ["db", "backend"]

    def test_save_multiple_memories(self, tmp_path, project_context):
        """Test that multiple saves append."""
        save_memory(project_context, "First")
        save_memory(project_context, "Second")

        memory_file = tmp_path / ".ayder" / "memory" / "memories.jsonl"
        lines = memory_file.read_text().strip().split('\n')
        assert len(lines) == 2


class TestLoadMemory:
    """Test load_memory() function."""

    def test_load_empty(self, tmp_path, project_context):
        """Test loading when no memories exist."""
        result = load_memory(project_context)
        assert isinstance(result, ToolSuccess)
        assert json.loads(result) == []

    def test_load_all_memories(self, tmp_path, project_context):
        """Test loading all memories."""
        save_memory(project_context, "Memory 1")
        save_memory(project_context, "Memory 2")

        result = load_memory(project_context)
        memories = json.loads(result)
        assert len(memories) == 2
        # Most recent first
        assert memories[0]["content"] == "Memory 2"
        assert memories[1]["content"] == "Memory 1"

    def test_load_filter_by_category(self, tmp_path, project_context):
        """Test loading with category filter."""
        save_memory(project_context, "Arch decision", category="architecture")
        save_memory(project_context, "Bug found", category="bugs")

        result = load_memory(project_context, category="architecture")
        memories = json.loads(result)
        assert len(memories) == 1
        assert memories[0]["content"] == "Arch decision"

    def test_load_filter_by_query(self, tmp_path, project_context):
        """Test loading with search query."""
        save_memory(project_context, "Use JWT for authentication")
        save_memory(project_context, "Database uses PostgreSQL")

        result = load_memory(project_context, query="JWT")
        memories = json.loads(result)
        assert len(memories) == 1
        assert "JWT" in memories[0]["content"]

    def test_load_with_limit(self, tmp_path, project_context):
        """Test loading with limit."""
        for i in range(5):
            save_memory(project_context, f"Memory {i}")

        result = load_memory(project_context, limit=3)
        memories = json.loads(result)
        assert len(memories) == 3

    def test_load_query_case_insensitive(self, tmp_path, project_context):
        """Test that query search is case-insensitive."""
        save_memory(project_context, "Use PostgreSQL for the database")

        result = load_memory(project_context, query="postgresql")
        memories = json.loads(result)
        assert len(memories) == 1


class TestMemoryManager:
    """Test MemoryManager class for LLM-based checkpoint operations."""

    @pytest.fixture
    def memory_manager(self, tmp_path):
        """Create a MemoryManager with mocked dependencies."""
        project_ctx = ProjectContext(str(tmp_path))
        llm = Mock()
        tool_executor = Mock()
        cm = Mock()
        return MemoryManager(project_ctx, llm, tool_executor, cm)

    def test_initialization(self, tmp_path):
        """Test MemoryManager initialization."""
        project_ctx = ProjectContext(str(tmp_path))
        llm = Mock()
        tool_executor = Mock()
        cm = Mock()
        
        mm = MemoryManager(project_ctx, llm, tool_executor, cm)
        
        assert mm.project_ctx == project_ctx
        assert mm.llm == llm
        assert mm.tool_executor == tool_executor
        assert mm.cm == cm
        assert mm._cycle_count == 0

    def test_initialization_without_optional_deps(self, tmp_path):
        """Test MemoryManager initialization without optional dependencies."""
        project_ctx = ProjectContext(str(tmp_path))
        
        mm = MemoryManager(project_ctx)
        
        assert mm.llm is None
        assert mm.tool_executor is None
        assert mm.cm is None

    def test_build_checkpoint_prompt(self, memory_manager):
        """Test building checkpoint prompt."""
        summary = "Test conversation summary"
        prompt = memory_manager.build_checkpoint_prompt(summary)
        
        assert "Test conversation summary" in prompt
        assert "write_file" in prompt or "checkpoint" in prompt.lower()

    def test_build_restore_prompt(self, memory_manager, tmp_path):
        """Test building restore prompt."""
        # Create a checkpoint file
        checkpoint_file = tmp_path / ".ayder" / "memory" / "current_memory.md"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text("Saved checkpoint content")
        
        # Update memory manager's checkpoint file path
        memory_manager._checkpoint_file = checkpoint_file
        
        prompt = memory_manager.build_restore_prompt()
        
        assert "Saved checkpoint content" in prompt
        assert "current_memory.md" in prompt

    def test_build_restore_prompt_with_content(self, memory_manager):
        """Test building restore prompt with provided content."""
        content = "Custom checkpoint content"
        prompt = memory_manager.build_restore_prompt(content)
        
        assert "Custom checkpoint content" in prompt

    def test_build_quick_restore_message_with_checkpoint(self, memory_manager, tmp_path):
        """Test building quick restore message when checkpoint exists."""
        # Create a checkpoint file
        checkpoint_file = tmp_path / ".ayder" / "memory" / "current_memory.md"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text("Checkpoint data")
        
        memory_manager._checkpoint_file = checkpoint_file
        
        message = memory_manager.build_quick_restore_message()
        
        assert "Checkpoint data" in message
        assert "SYSTEM: Context reset completed" in message

    def test_build_quick_restore_message_no_checkpoint(self, memory_manager):
        """Test building quick restore message when no checkpoint exists."""
        message = memory_manager.build_quick_restore_message()
        
        assert "No previous memory" in message or "Continuing task" in message

    def test_create_checkpoint_no_llm(self, memory_manager):
        """Test create_checkpoint returns False when no LLM."""
        memory_manager.llm = None
        session = Mock()
        
        result = memory_manager.create_checkpoint(session, "model", 4096, set(), False)
        
        assert result is False

    def test_create_checkpoint_no_tool_executor(self, memory_manager):
        """Test create_checkpoint returns False when no tool executor."""
        memory_manager.tool_executor = None
        session = Mock()
        
        result = memory_manager.create_checkpoint(session, "model", 4096, set(), False)
        
        assert result is False

    def test_create_checkpoint_success(self, memory_manager):
        """Test successful checkpoint creation."""
        session = Mock()
        session.get_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        
        # Mock LLM response
        mock_message = Mock()
        mock_message.content = "Checkpoint saved"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        memory_manager.llm.chat.return_value = mock_response
        memory_manager.tool_executor.tool_registry = Mock()
        memory_manager.tool_executor.tool_registry.get_schemas.return_value = []
        
        result = memory_manager.create_checkpoint(session, "model", 4096, set(), False)
        
        assert result is True
        assert memory_manager._cycle_count == 1
        session.add_message.assert_called()
        session.clear_messages.assert_called_once_with(keep_system=True)

    def test_create_checkpoint_with_tool_calls(self, memory_manager):
        """Test checkpoint creation when LLM makes tool calls."""
        session = Mock()
        session.get_messages.return_value = []
        
        # Mock LLM response with tool calls
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        memory_manager.llm.chat.return_value = mock_response
        memory_manager.tool_executor.tool_registry = Mock()
        memory_manager.tool_executor.tool_registry.get_schemas.return_value = []
        memory_manager.tool_executor.execute_tool_calls = Mock()
        
        result = memory_manager.create_checkpoint(session, "model", 4096, set(), False)
        
        assert result is True
        session.append_raw.assert_called_once_with(mock_message)
        memory_manager.tool_executor.execute_tool_calls.assert_called_once()

    def test_restore_from_checkpoint(self, memory_manager):
        """Test restore_from_checkpoint."""
        session = Mock()
        
        # Mock _read_checkpoint to return content
        memory_manager._read_checkpoint = Mock(return_value="Saved memory content")
        
        memory_manager.restore_from_checkpoint(session)
        
        session.clear_messages.assert_called_once_with(keep_system=True)
        session.add_message.assert_called_once()

    def test_build_conversation_summary(self, memory_manager):
        """Test building conversation summary."""
        session = Mock()
        session.get_messages.return_value = [
            {"role": "user", "content": "Hello world, this is a test message"},
            {"role": "assistant", "content": "Hi there, I can help you"},
        ]
        
        summary = memory_manager._build_conversation_summary(session)
        
        assert "[user]" in summary
        assert "[assistant]" in summary
        assert "Hello world" in summary

    def test_read_checkpoint(self, memory_manager, tmp_path):
        """Test reading checkpoint file."""
        # Create a checkpoint file
        checkpoint_file = tmp_path / ".ayder" / "memory" / "current_memory.md"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text("Test checkpoint data")
        
        memory_manager._checkpoint_file = checkpoint_file
        
        content = memory_manager._read_checkpoint()
        
        assert content == "Test checkpoint data"

    def test_read_checkpoint_no_file(self, memory_manager):
        """Test reading checkpoint when file doesn't exist."""
        content = memory_manager._read_checkpoint()
        
        assert content is None


class TestCreateMemoryManager:
    """Test create_memory_manager factory function."""

    def test_factory_creates_memory_manager(self, tmp_path):
        """Test that factory creates a MemoryManager."""
        mm = create_memory_manager(str(tmp_path))
        
        assert isinstance(mm, MemoryManager)
        assert mm.project_ctx.root == tmp_path
