"""
Theme manager for ayder-cli TUI.

Handles loading and applying themes for the terminal user interface.
Themes can be configured in ~/.ayder/config.toml under [ui] section:

[ui]
theme = "claude"  # or "original", or another theme name
"""

from pathlib import Path
from typing import Optional

from ayder_cli.themes import Theme, get_theme, get_default_theme, list_themes, get_theme_names
from ayder_cli.core.config import Config, load_config


class ThemeManager:
    """
    Manages TUI themes for ayder-cli.
    
    Provides theme loading, CSS retrieval, and theme switching capabilities.
    """
    
    _instance: Optional["ThemeManager"] = None
    _current_theme: Optional[Theme] = None
    
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
                return ui_section.get("theme", "claude")
            return self._config.get("theme", "claude")
        else:
            # Handle Config object format
            # Check if theme attribute exists (for future Config updates)
            return getattr(self._config, "theme", "claude")
    
    def _apply_theme(self, theme_name: str) -> None:
        """Apply a theme by name."""
        theme = get_theme(theme_name)
        if theme is None:
            # Fall back to default if theme not found
            available = get_theme_names()
            if theme_name != "claude":
                # Only warn for non-default themes
                print(f"[ThemeManager] Warning: Theme '{theme_name}' not found. "
                      f"Available: {', '.join(available)}. Using default.")
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


def get_available_themes() -> list[str]:
    """Get list of available theme names."""
    return get_theme_names()
