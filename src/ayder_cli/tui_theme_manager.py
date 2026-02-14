"""Backward-compatibility shim — real code lives in ayder_cli.tui.theme_manager."""

from ayder_cli.tui.theme_manager import (
    ThemeManager,
    get_theme_css,
    get_available_themes,
)  # noqa: F401
