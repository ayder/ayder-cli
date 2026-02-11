"""Tests for checkpoint_manager.py module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from ayder_cli.checkpoint_manager import CheckpointManager, CHECKPOINT_FILE_NAME
from ayder_cli.core.context import ProjectContext


class TestCheckpointManager:
    """Test CheckpointManager class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project context."""
        return ProjectContext(str(tmp_path))

    @pytest.fixture
    def checkpoint_manager(self, temp_project):
        """Create a CheckpointManager instance."""
        return CheckpointManager(temp_project)

    def test_initialization(self, temp_project):
        """Test CheckpointManager initialization."""
        cm = CheckpointManager(temp_project)
        
        assert cm.project_ctx == temp_project
        assert cm._cycle_count == 0
        assert cm._last_checkpoint_content is None
        assert cm.checkpoint_file_path == temp_project.root / ".ayder" / "memory" / CHECKPOINT_FILE_NAME

    def test_initialization_restores_cycle_count(self, temp_project):
        """Test cycle count is restored from existing checkpoint."""
        # Create an existing checkpoint file with cycle 3
        checkpoint_dir = temp_project.root / ".ayder" / "memory"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = checkpoint_dir / CHECKPOINT_FILE_NAME
        checkpoint_file.write_text(
            "# Memory Checkpoint (Cycle 3)\nGenerated: 2024-01-01\n\n---\n\ncontent",
            encoding="utf-8"
        )
        
        cm = CheckpointManager(temp_project)
        
        assert cm.cycle_count == 3

    def test_ensure_checkpoint_dir(self, checkpoint_manager):
        """Test checkpoint directory creation."""
        cm = checkpoint_manager
        cm._ensure_checkpoint_dir()
        
        assert cm._checkpoint_dir.exists()
        assert cm._checkpoint_dir.is_dir()

    def test_has_saved_checkpoint_false(self, checkpoint_manager):
        """Test has_saved_checkpoint returns False when no checkpoint exists."""
        assert checkpoint_manager.has_saved_checkpoint() is False

    def test_has_saved_checkpoint_true(self, checkpoint_manager):
        """Test has_saved_checkpoint returns True when checkpoint file exists."""
        cm = checkpoint_manager
        cm._ensure_checkpoint_dir()
        cm._checkpoint_file.write_text("test checkpoint", encoding="utf-8")
        
        assert cm.has_saved_checkpoint() is True

    def test_read_checkpoint_no_file(self, checkpoint_manager):
        """Test read_checkpoint returns None when no file exists."""
        assert checkpoint_manager.read_checkpoint() is None

    def test_read_checkpoint_with_content(self, checkpoint_manager):
        """Test read_checkpoint returns content when file exists."""
        cm = checkpoint_manager
        cm._ensure_checkpoint_dir()
        test_content = "# Test Checkpoint\nSome content here"
        cm._checkpoint_file.write_text(test_content, encoding="utf-8")
        
        result = cm.read_checkpoint()
        assert result == test_content

    def test_save_checkpoint_success(self, checkpoint_manager):
        """Test successful checkpoint save."""
        cm = checkpoint_manager
        content = "Task progress summary"
        
        result = cm.save_checkpoint(content)
        
        assert result.is_success is True
        assert "Checkpoint saved" in str(result)
        assert cm._checkpoint_file.exists()
        
        # Check file content
        saved_content = cm._checkpoint_file.read_text(encoding="utf-8")
        assert "# Memory Checkpoint (Cycle 1)" in saved_content
        assert content in saved_content
        assert "Generated:" in saved_content

    def test_save_checkpoint_increments_cycle(self, checkpoint_manager):
        """Test that save_checkpoint increments cycle count."""
        cm = checkpoint_manager
        
        cm.save_checkpoint("content 1")
        assert cm.cycle_count == 1
        
        cm.save_checkpoint("content 2")
        assert cm.cycle_count == 2

    def test_clear_checkpoint(self, checkpoint_manager):
        """Test clearing checkpoint file."""
        cm = checkpoint_manager
        cm._ensure_checkpoint_dir()
        cm._checkpoint_file.write_text("content", encoding="utf-8")
        cm._cycle_count = 5
        
        result = cm.clear_checkpoint()
        
        assert result.is_success is True
        assert not cm._checkpoint_file.exists()
        assert cm.cycle_count == 0

    def test_clear_checkpoint_no_file(self, checkpoint_manager):
        """Test clearing checkpoint when file doesn't exist."""
        cm = checkpoint_manager
        
        result = cm.clear_checkpoint()
        
        assert result.is_success is True

    def test_checkpoint_file_path_property(self, checkpoint_manager, temp_project):
        """Test checkpoint_file_path property returns correct path."""
        cm = checkpoint_manager
        expected = temp_project.root / ".ayder" / "memory" / CHECKPOINT_FILE_NAME
        assert cm.checkpoint_file_path == expected

    def test_cycle_count_property(self, checkpoint_manager):
        """Test cycle_count property."""
        cm = checkpoint_manager
        assert cm.cycle_count == 0
        
        cm._cycle_count = 5
        assert cm.cycle_count == 5


class TestCreateCheckpointManager:
    """Test create_checkpoint_manager factory function."""

    def test_factory_creates_checkpoint_manager(self, tmp_path):
        """Test that factory creates a CheckpointManager."""
        from ayder_cli.checkpoint_manager import create_checkpoint_manager
        
        cm = create_checkpoint_manager(str(tmp_path))
        
        assert isinstance(cm, CheckpointManager)
        assert cm.project_ctx.root == tmp_path
