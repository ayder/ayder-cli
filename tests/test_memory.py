"""Tests for memory management."""

import json
import pytest
from pathlib import Path
from ayder_cli.memory import save_memory, load_memory
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


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
