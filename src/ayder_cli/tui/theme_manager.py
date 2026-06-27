"""
Theme manager for ayder-cli TUI.

Handles loading and applying themes for the terminal user interface.
Themes can be configured in ~/.ayder/config.toml under [ui] section:

[ui]
theme = "ayder"       # layout (default): ayder / ayder-dark / ayder-light, or claude
palette = "auto"      # App.theme for the ayder layout: auto (ansi passthrough,
                      # respects the terminal) or an RGB Textual theme to overlay
                      # a fixed palette on the same layout: monokai, dracula,
                      # nord, gruvbox, tokyo-night … (these paint their own
                      # background and do NOT respect the terminal background).
"""

from typing import Optional

from ayder_cli.themes import (
    Theme,
    get_theme,
    get_default_theme,
    list_themes,
    get_theme_names,
)
from ayder_cli.core.config import Config, load_config

# Friendly palette names -> the Textual App.theme that backs them. Anything not
# listed is passed through verbatim as a Textual theme name (monokai, dracula …).
_PALETTE_TO_TEXTUAL = {
    "ansi-dark": "ayder-dark",
    "ansi-light": "ayder-light",
}


class ThemeManager:
    """
    Manages TUI themes for ayder-cli.

    Provides theme loading, CSS retrieval, and theme switching capabilities.
    """

    _instance: Optional["ThemeManager"] = None
    _current_theme: Optional[Theme] = None
    _initialized: bool = False

    def __new__(cls, config: Optional[Config] = None) -> "ThemeManager":
        """Singleton pattern to ensure consistent theme state."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the theme manager.

        Args:
            config: Optional config object. If not provided, loads from file.
        """
        if self._initialized:
            return

        self._config = config or load_config()
        self._initialized = True

        # Load theme from config or use default
        self._load_theme_from_config()

    def _load_theme_from_config(self) -> None:
        """Load the theme specified in config, or use default."""
        theme_name = self._get_theme_name_from_config()
        self._apply_theme(theme_name)

    def _get_theme_name_from_config(self) -> str:
        """Extract theme name from config, handling both dict and object formats."""
        if isinstance(self._config, dict):
            # Handle dict format (for compatibility)
            ui_section = self._config.get("ui", {})
            if isinstance(ui_section, dict):
                return ui_section.get("theme", "ayder")
            return self._config.get("theme", "ayder")
        else:
            # Handle Config object format
            # Check if theme attribute exists (for future Config updates)
            return getattr(self._config, "theme", "ayder")

    def _get_palette_from_config(self) -> str:
        """Extract the [ui] palette value from config (dict or Config object)."""
        if isinstance(self._config, dict):
            ui_section = self._config.get("ui", {})
            if isinstance(ui_section, dict):
                return ui_section.get("palette", "auto")
            return self._config.get("palette", "auto")
        return getattr(self._config, "palette", "auto")

    def _apply_theme(self, theme_name: str) -> None:
        """Apply a theme by name."""
        theme = get_theme(theme_name)
        if theme is None:
            # Fall back to default if theme not found
            available = get_theme_names()
            if theme_name != "ayder":
                # Only warn for non-default themes
                print(
                    f"[ThemeManager] Warning: Theme '{theme_name}' not found. "
                    f"Available: {', '.join(available)}. Using default."
                )
            theme = get_default_theme()

        self._current_theme = theme

    @property
    def current_theme(self) -> Theme:
        """Get the currently active theme."""
        if self._current_theme is None:
            self._current_theme = get_default_theme()
        return self._current_theme

    @property
    def css(self) -> str:
        """Get the CSS for the current theme."""
        return self.current_theme.css

    def get_css(self) -> str:
        """Get the CSS string for the current theme."""
        return self.css

    @property
    def ansi_color(self) -> bool:
        """Whether the current theme wants ANSI passthrough (``ansi_color=True``)."""
        return self.current_theme.ansi

    def get_ansi_color(self) -> bool:
        """Whether the current theme wants ANSI passthrough."""
        return self.ansi_color

    @property
    def textual_theme(self) -> Optional[str]:
        """The current layout theme's *default* palette (its ``textual_theme``).

        This ignores any ``[ui] palette`` override — use :attr:`palette` for the
        effective Textual ``App.theme``.
        """
        return self.current_theme.textual_theme

    def get_textual_theme(self) -> Optional[str]:
        """The current layout theme's default palette (ignores ``[ui] palette``)."""
        return self.textual_theme

    @property
    def palette(self) -> Optional[str]:
        """The effective Textual ``App.theme`` to paint the layout with.

        Resolution:
          1. An explicit ``[ui] palette`` (anything other than ``"auto"``):
             ``ansi-dark``/``ansi-light`` map to the ayder ANSI themes; any other
             value is passed through as a Textual theme name (monokai, dracula …).
          2. Otherwise the layout theme's own default palette (``textual_theme``).

        Returns ``None`` when the layout names no palette and none was set — e.g.
        the self-contained RGB ``claude`` theme, which keeps Textual's default.
        """
        theme = self.current_theme
        default = theme.textual_theme
        raw = (self._get_palette_from_config() or "auto").strip()
        # A self-contained RGB theme (claude: no textual_theme, not ansi) keeps
        # Textual's default theme; an explicit palette would not change its
        # hard-coded RGB CSS, so it is intentionally ignored there.
        if default is None and not theme.ansi:
            return None
        if raw and raw != "auto":
            return _PALETTE_TO_TEXTUAL.get(raw, raw)
        return default

    def get_palette(self) -> Optional[str]:
        """The effective Textual ``App.theme`` to paint the layout with."""
        return self.palette

    def set_theme(self, theme_name: str) -> bool:
        """
        Change the active theme at runtime.

        Args:
            theme_name: Name of the theme to activate

        Returns:
            True if theme was changed, False if theme not found
        """
        theme = get_theme(theme_name)
        if theme is None:
            return False

        self._current_theme = theme
        return True

    def list_available_themes(self) -> list[Theme]:
        """List all available themes."""
        return list_themes()

    def get_available_theme_names(self) -> list[str]:
        """Get names of all available themes."""
        return get_theme_names()

    def reload(self) -> None:
        """Reload theme from config (useful after config file changes)."""
        self._config = load_config()
        self._load_theme_from_config()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None
        cls._current_theme = None


# Convenience function to get CSS without managing the manager directly
def get_theme_css(config: Optional[Config] = None) -> str:
    """
    Get the CSS for the current theme.

    This is a convenience function that creates/uses the ThemeManager singleton.

    Args:
        config: Optional config override

    Returns:
        CSS string for the current theme
    """
    manager = ThemeManager(config)
    return manager.get_css()


def get_theme_ansi_color(config: Optional[Config] = None) -> bool:
    """
    Whether the current theme wants ANSI passthrough (``ansi_color=True``).

    When True, the app emits real ANSI escapes for the 16-colour palette and
    ``ansi_default`` instead of converting them to RGB, so the user's terminal
    colours (including the background) are respected on every terminal.
    """
    manager = ThemeManager(config)
    return manager.get_ansi_color()


def get_theme_textual_theme(config: Optional[Config] = None) -> Optional[str]:
    """
    The current layout theme's *default* palette (ignores ``[ui] palette``).

    ANSI themes (ayder-dark/ayder-light) name a Textual theme whose every
    surface is ``ansi_default`` — that is what makes Textual render the
    terminal's own background/palette (including the TextArea input). For the
    effective ``App.theme`` (honouring ``[ui] palette``), use
    :func:`get_theme_palette`.
    """
    manager = ThemeManager(config)
    return manager.get_textual_theme()


def get_theme_palette(config: Optional[Config] = None) -> Optional[str]:
    """
    The effective Textual ``App.theme`` (palette) for the active layout, or None.

    Honours ``[ui] palette``: ``auto`` (the default) keeps the layout's own
    terminal-respecting ANSI palette; an RGB Textual theme name (monokai,
    dracula, nord …) overlays a fixed palette on the same layout. ``None`` means
    keep Textual's default theme (the self-contained ``claude`` theme).
    """
    manager = ThemeManager(config)
    return manager.get_palette()


def get_available_themes() -> list[str]:
    """Get list of available theme names."""
    return get_theme_names()
