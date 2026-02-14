"""
Themes package for ayder-cli TUI.

Provides theme management and CSS styling for the terminal user interface.
Themes can be configured via the config file under [ui] section.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable
from pathlib import Path


@dataclass(frozen=True)
class Theme:
    """A TUI theme containing CSS styles and metadata."""

    name: str
    description: str
    css: str

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
    """Get the default theme (claude)."""
    return _THEME_REGISTRY.get("claude") or list(_THEME_REGISTRY.values())[0]


def list_themes() -> list[Theme]:
    """List all available themes."""
    return list(_THEME_REGISTRY.values())


def get_theme_names() -> list[str]:
    """Get list of all theme names."""
    return list(_THEME_REGISTRY.keys())


# Import and register built-in themes
def _load_builtin_themes():
    """Load all built-in themes."""
    from . import original
    from . import claude


# Auto-load themes on import
_load_builtin_themes()
