import os
from pathlib import Path
from dataclasses import dataclass
from ayder_cli.core.config import Config


class ProjectContext:
    """Handles path validation and translation between relative and absolute paths.

    Provides sandboxing to prevent path traversal attacks while correctly handling
    macOS ~ paths.
    """

    def __init__(self, root_dir: str = "."):
        """Initialize ProjectContext with a root directory.

        Args:
            root_dir: Root directory path (defaults to current directory)
        """
        expanded_root = os.path.expanduser(root_dir)
        self.root = Path(expanded_root).resolve()

    def validate_path(self, file_path: str) -> Path:
        """Validate and resolve a file path, ensuring it stays within the project root.

        Args:
            file_path: Path to validate (relative or absolute)

        Returns:
            Resolved absolute Path object

        Raises:
            ValueError: If path is outside the project root
        """
        clean_path = os.path.expanduser(str(file_path).strip())

        if Path(clean_path).is_absolute():
            target_path = Path(clean_path).resolve()
        else:
            target_path = (self.root / clean_path).resolve()

        if not target_path.is_relative_to(self.root):
            raise ValueError(
                f"Security Alert: Path '{target_path}' is outside project root '{self.root}'"
            )

        return target_path

    def to_relative(self, absolute_path: Path) -> str:
        """Convert an absolute path to relative path for LLM output.

        Args:
            absolute_path: Absolute Path object

        Returns:
            Relative path as string, or absolute path string if conversion fails
        """
        try:
            return str(absolute_path.relative_to(self.root))
        except ValueError:
            return str(absolute_path)


@dataclass
class SessionContext:
    """Unified context for a chat session.
    
    Holds configuration, project-specific path context, chat history, runtime state,
    and enhanced system prompt.
    """
    config: Config
    project: ProjectContext
    messages: list
    state: dict
    system_prompt: str = ""           # Enhanced system prompt with project structure