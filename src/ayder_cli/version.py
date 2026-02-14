"""Version information for ayder-cli."""

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _get_version_from_pyproject() -> str | None:
    """Read version directly from pyproject.toml."""
    # Look for pyproject.toml starting from this file's location
    current_dir = Path(__file__).parent
    for parent in [current_dir, *current_dir.parents]:
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8")
            match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
            if match:
                return match.group(1)
    return None


def get_app_version():
    """
    Retrieve the version from installed package metadata or pyproject.toml.

    First tries to get version from installed package metadata.
    If not installed (e.g., running from source), reads directly from pyproject.toml.
    Returns 'unknown (dev)' if neither method works.
    """
    # Try installed package metadata first
    try:
        return version("ayder-cli")
    except PackageNotFoundError:
        pass

    # Fallback: read from pyproject.toml
    version_from_pyproject = _get_version_from_pyproject()
    if version_from_pyproject:
        return version_from_pyproject

    return "unknown (dev)"


# Expose version globally if other modules need it
__version__ = get_app_version()
