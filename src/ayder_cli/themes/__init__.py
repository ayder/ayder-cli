"""
Themes package for ayder-cli TUI.

Provides theme management and CSS styling for the terminal user interface.
Themes can be configured via the config file under [ui] section.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path  # noqa: F401


@dataclass(frozen=True)
class Theme:
    """A TUI theme containing CSS styles and metadata."""

    name: str
    description: str
    css: str
    # When True, this is an ANSI-passthrough theme: the app emits the 16-colour
    # ANSI palette (and ``ansi_default``) as real ANSI escapes instead of
    # converting them to RGB, so the user's terminal colours — including their
    # background — are respected on truecolor terminals too.
    ansi: bool = False
    # Name of the Textual built-in/registered theme (``App.theme``) to activate
    # for this CSS theme, e.g. "ayder-dark"/"ayder-light". None keeps Textual's
    # default theme. This is how an ANSI theme gets terminal-default surfaces.
    textual_theme: Optional[str] = None

    def __post_init__(self):
        # Validate that CSS is not empty
        if not self.css or not self.css.strip():
            raise ValueError(f"Theme '{self.name}' cannot have empty CSS")


# Registry of available themes
_THEME_REGISTRY: Dict[str, Theme] = {}


def register_theme(theme: Theme) -> None:
    """Register a theme in the global registry."""
    _THEME_REGISTRY[theme.name] = theme


def get_theme(name: str) -> Optional[Theme]:
    """Get a theme by name, returns None if not found."""
    return _THEME_REGISTRY.get(name)


def get_default_theme() -> Theme:
    """Get the default theme (ayder — terminal-respecting ANSI passthrough)."""
    return (
        _THEME_REGISTRY.get("ayder")
        or _THEME_REGISTRY.get("claude")
        or list(_THEME_REGISTRY.values())[0]
    )


def list_themes() -> list[Theme]:
    """List all available themes."""
    return list(_THEME_REGISTRY.values())


def get_theme_names() -> list[str]:
    """Get list of all theme names."""
    return list(_THEME_REGISTRY.keys())


# Import and register built-in themes
def _load_builtin_themes():
    """Load all built-in themes."""
    from . import claude  # noqa: F401
    from . import ayder  # noqa: F401


# Auto-load themes on import
_load_builtin_themes()
