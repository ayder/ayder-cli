import getpass
import hashlib
import os
import secrets
import stat
import tempfile
from datetime import datetime
from pathlib import Path


def _default_scratch_base() -> Path:
    """``/tmp/ayder-<uid>``: where models already look for temporary space."""
    if hasattr(os, "getuid"):
        return Path("/tmp") / f"ayder-{os.getuid()}"
    return Path(tempfile.gettempdir()) / f"ayder-{getpass.getuser()}"


# Per-user parent of every session scratch directory; tests point it elsewhere.
SCRATCH_BASE = _default_scratch_base()


def _owned_private_dir(path: Path) -> bool:
    """True when ``path`` itself (not a symlink) is a directory this user owns."""
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        return False
    return not hasattr(os, "getuid") or st.st_uid == os.getuid()


def new_scratch_dir(
    project_root: Path | str, parent: Path | None = None, label: str = "agent"
) -> Path | None:
    """Create a private (0700) scratch directory and return it.

    Without ``parent`` it is a session directory,
    ``SCRATCH_BASE/<project>-<hash>/<YYYYmmdd-HHMMSS>-<hex>``; with ``parent``
    it is ``<parent>/<label>-<hex>``. Returns None when the per-user base is a
    symlink, belongs to someone else, or cannot be created: the session then
    runs without one and the sandbox stays the project root.
    """
    try:
        if parent is None:
            SCRATCH_BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not _owned_private_dir(SCRATCH_BASE):
                return None
            os.chmod(SCRATCH_BASE, 0o700)
            root = Path(project_root).resolve()
            digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
            folder = SCRATCH_BASE / f"{root.name}-{digest}"
            folder.mkdir(mode=0o700, exist_ok=True)
            name = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        else:
            folder = Path(parent)
            name = f"{label}-{secrets.token_hex(3)}"
        path = folder / name
        path.mkdir(mode=0o700)
        return path
    except OSError:
        return None


class PathOutsideSandboxError(ValueError):
    """A path resolves outside the project root, scratch dir, or a confined directory."""


class ProjectContext:
    """Handles path validation and translation between relative and absolute paths.

    Provides sandboxing to prevent path traversal attacks while correctly handling
    macOS ~ paths.
    """

    def __init__(self, root_dir: str = ".", scratch_dir: Path | str | None = None):
        """Initialize ProjectContext with a root directory.

        Args:
            root_dir: Root directory path (defaults to current directory)
            scratch_dir: The session scratch directory, a second root the file
                tools may use (see ``new_scratch_dir``); None allows only the root.
        """
        expanded_root = os.path.expanduser(root_dir)
        self.root = Path(expanded_root).resolve()
        self.scratch_dir = Path(scratch_dir).resolve() if scratch_dir is not None else None

    def validate_path(self, file_path: str) -> Path:
        """Validate and resolve a file path, ensuring it stays within the project root
        or the session scratch directory.

        Args:
            file_path: Path to validate (relative or absolute)

        Returns:
            Resolved absolute Path object

        Raises:
            PathOutsideSandboxError: If path is outside the project root
        """
        clean_path = os.path.expanduser(str(file_path).strip())

        if Path(clean_path).is_absolute():
            target_path = Path(clean_path).resolve()
        else:
            target_path = (self.root / clean_path).resolve()

        in_scratch = self.scratch_dir is not None and target_path.is_relative_to(self.scratch_dir)
        if not target_path.is_relative_to(self.root) and not in_scratch:
            raise PathOutsideSandboxError(
                f"Security Alert: Path '{target_path}' is outside project root '{self.root}'"
            )

        return target_path

    def harness_dir(self, *parts: str) -> Path:
        """Return ``<root>/.ayder/<parts>``, refusing a location outside the root.

        ``validate_path`` resolves symlinks, so a ``.ayder/<parts>`` symlink that
        points outside the project raises instead of redirecting writes.
        The directory is not created.

        Raises:
            PathOutsideSandboxError: If the resolved directory is outside the project root.
        """
        return self.validate_path(str(Path(".ayder", *parts)))

    @staticmethod
    def within(directory: Path, path: Path | str) -> Path:
        """Return ``path`` unchanged if it resolves inside ``directory``.

        The resolved form is only checked, never returned, so names and
        relative paths stay stable when an in-directory symlink is followed.
        ``os.path.realpath`` is used rather than ``Path.resolve``, which also
        stats the final target. Resolving still lstats and reads links along
        the path, including outside components; what it never does is read or
        follow-stat the target's content, so a refused entry stays unread.

        Raises:
            PathOutsideSandboxError: If ``path`` resolves outside ``directory``.
        """
        resolved = Path(os.path.realpath(path))
        if not resolved.is_relative_to(Path(os.path.realpath(directory))):
            raise PathOutsideSandboxError(
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
