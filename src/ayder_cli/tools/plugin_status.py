"""Plugin status-badge registry.

A lightweight, process-global registry that plugins use to publish a status
badge (a short label plus a colour) for display in the TUI status bar. The
mcp-tool plugin, for example, calls ``set_status("mcp", "MCP: news-digest",
"green")`` once it connects to its MCP servers, and ``set_status("mcp", "MCP",
"red")`` when configured servers are unreachable.

The TUI ``StatusBar`` reads :func:`get_all` to render the badges. Keeping this
in ayder core (rather than inside a plugin) means the badge survives even when
the plugin's own modules are loaded under throwaway names during discovery, and
gives the plugin a stable import target instead of a no-op fallback.
"""

from __future__ import annotations

# plugin name -> (label, colour). Colour is a Rich colour/style name ("green").
_status: dict[str, tuple[str, str]] = {}


def set_status(name: str, label: str, color: str) -> None:
    """Register or update a plugin's status badge."""
    _status[name] = (label, color)


def get_all() -> dict[str, tuple[str, str]]:
    """Return a copy of all registered status badges (name -> (label, color))."""
    return dict(_status)


def clear() -> None:
    """Remove all registered badges (primarily for tests)."""
    _status.clear()
