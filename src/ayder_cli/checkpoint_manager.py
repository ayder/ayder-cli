"""
Checkpoint Manager for handling checkpoint file I/O operations.

This module provides low-level file operations for agent checkpoint/reset cycles:
1. Saving checkpoint content to disk
2. Reading checkpoint content from disk

The LLM interaction logic for creating checkpoints is handled by MemoryManager
in memory.py, which uses this module for file I/O operations.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


CHECKPOINT_FILE_NAME = "current_memory.md"


class CheckpointManager:
    """Manages checkpoint file I/O operations for long-running agent sessions.

    This class is responsible for:
    - Reading and writing checkpoint files to disk
    - Tracking checkpoint cycle count
    - Checking for existing checkpoints

    It does NOT interact with the LLM. For LLM-based checkpoint operations,
    use MemoryManager from memory.py.

    Checkpoint file format:
        # Memory Checkpoint (Cycle N)
        Generated: <iso_timestamp>

        ---

        <checkpoint content>
    """

    def __init__(self, project_ctx: ProjectContext):
        """Initialize CheckpointManager with project context.

        Args:
            project_ctx: Project context for path resolution
        """
        self.project_ctx = project_ctx
        self._checkpoint_dir = project_ctx.root / ".ayder" / "memory"
        self._checkpoint_file = self._checkpoint_dir / CHECKPOINT_FILE_NAME
        self._cycle_count = 0
        self._last_checkpoint_content: Optional[str] = None

        # Try to restore cycle count from existing checkpoint
        self._restore_cycle_count_from_file()

    def _ensure_checkpoint_dir(self) -> None:
        """Ensure the checkpoint directory exists."""
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _restore_cycle_count_from_file(self) -> None:
        """Restore cycle count from existing checkpoint file header."""
        if not self._checkpoint_file.exists():
            return

        try:
            content = self._checkpoint_file.read_text(encoding="utf-8")
            # Parse cycle number from header: "# Memory Checkpoint (Cycle N)"
            match = re.search(r"# Memory Checkpoint \(Cycle (\d+)\)", content)
            if match:
                self._cycle_count = int(match.group(1))
        except Exception:
            pass  # Keep cycle_count as 0 if parsing fails

    @property
    def checkpoint_file_path(self) -> Path:
        """Get the path to the current checkpoint file."""
        return self._checkpoint_file

    @property
    def cycle_count(self) -> int:
        """Get the number of checkpoint cycles completed."""
        return self._cycle_count

    def has_saved_checkpoint(self) -> bool:
        """Check if there's a saved checkpoint file."""
        return self._checkpoint_file.exists()

    def read_checkpoint(self) -> Optional[str]:
        """Read the current checkpoint content if it exists.

        Returns:
            Checkpoint content as string, or None if no checkpoint exists
        """
        if not self._checkpoint_file.exists():
            return None
        try:
            return self._checkpoint_file.read_text(encoding="utf-8")
        except Exception:
            return None

    def save_checkpoint(self, content: str) -> ToolSuccess | ToolError:
        """Save checkpoint content directly to the checkpoint file.

        Args:
            content: The checkpoint content to save

        Returns:
            ToolSuccess on success
        """
        try:
            self._ensure_checkpoint_dir()

            # Add timestamp and cycle info to the checkpoint
            new_cycle = self._cycle_count + 1
            header = f"""# Memory Checkpoint (Cycle {new_cycle})
Generated: {datetime.now().isoformat()}

---

"""
            full_content = header + content

            self._checkpoint_file.write_text(full_content, encoding="utf-8")

            self._cycle_count = new_cycle
            self._last_checkpoint_content = content

            return ToolSuccess(f"Checkpoint saved to {self._checkpoint_file}")
        except Exception as e:
            return ToolError(f"Failed to save checkpoint: {str(e)}", "execution")

    def clear_checkpoint(self) -> ToolSuccess | ToolError:
        """Clear the checkpoint file.

        Returns:
            ToolSuccess on success
        """
        try:
            if self._checkpoint_file.exists():
                self._checkpoint_file.unlink()
            self._cycle_count = 0
            self._last_checkpoint_content = None
            return ToolSuccess("Checkpoint file cleared")
        except Exception as e:
            return ToolError(f"Failed to clear checkpoint: {str(e)}", "execution")


def create_checkpoint_manager(project_root: str = ".") -> CheckpointManager:
    """Factory function to create a CheckpointManager instance.

    Args:
        project_root: Project root directory path

    Returns:
        Configured CheckpointManager instance
    """
    from ayder_cli.core.context import ProjectContext

    project_ctx = ProjectContext(project_root)
    return CheckpointManager(project_ctx)
