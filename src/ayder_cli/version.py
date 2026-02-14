"""Version information for ayder-cli."""

from importlib.metadata import version, PackageNotFoundError


def get_app_version():
    """
    Retrieve the version from the installed package metadata.

    Returns 'unknown (dev)' if the package is not installed (e.g., running raw script).
    """
    try:
        # CRITICAL: This string must match 'name' in pyproject.toml
        return version("ayder-cli")
    except PackageNotFoundError:
        return "unknown (dev)"


# Expose version globally if other modules need it
__version__ = get_app_version()
