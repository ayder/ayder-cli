"""
Centralized console instance for Rich UI.

This module provides a global Console instance that should be used
across the application for consistent styling and output.
"""

from pathlib import Path
from rich.console import Console
from rich.theme import Theme

# Custom theme for ayder-cli
CUSTOM_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "tool_call": "yellow",
        "user": "cyan",
        "assistant": "green",
        "border": "bright_black",
    }
)

# Global console instance
console = Console(theme=CUSTOM_THEME)


def get_console() -> Console:
    """Get the global console instance."""
    return console


# Map file extensions to syntax languages
EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".xml": "xml",
    ".dockerfile": "dockerfile",
}


def get_language_from_path(file_path: str) -> str:
    """Detect language from file extension for syntax highlighting."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, "text")
