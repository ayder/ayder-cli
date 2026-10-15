import os
from pathlib import Path


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

    def harness_dir(self, *parts: str) -> Path:
        """Return ``<root>/.ayder/<parts>``, refusing a location outside the root.

        ``validate_path`` resolves symlinks, so a ``.ayder/<parts>`` symlink that
        points outside the project raises instead of redirecting writes.
        The directory is not created.

        Raises:
            ValueError: If the resolved directory is outside the project root.
        """
        return self.validate_path(str(Path(".ayder", *parts)))

    @staticmethod
    def within(directory: Path, path: Path | str) -> Path:
        """Return ``path`` unchanged if it resolves inside ``directory``.

        The resolved form is only checked, never returned, so names and
        relative paths stay stable when an in-directory symlink is followed.
        ``os.path.realpath`` is used rather than ``Path.resolve``, which also
        stats the final target: an outward entry is never followed or stat-ed.

        Raises:
            ValueError: If ``path`` resolves outside ``directory``.
        """
        resolved = Path(os.path.realpath(path))
        if not resolved.is_relative_to(Path(os.path.realpath(directory))):
            raise ValueError(
                f"Security Alert: Path '{resolved}' is outside '{directory}'"
            )
        return Path(path)

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
