"""Tests for the plugin badge registry (ayder_cli.tools.plugin_status).

Plugins (e.g. mcp-tool) call set_status() to publish a status badge; the TUI
StatusBar reads get_all() to render it. The registry is process-global, so each
test clears it first.
"""

from ayder_cli.tools import plugin_status


def setup_function() -> None:
    plugin_status.clear()


def test_set_and_get_status():
    plugin_status.set_status("mcp", "MCP", "green")
    assert plugin_status.get_all() == {"mcp": ("MCP", "green")}


def test_overwrite_status():
    plugin_status.set_status("mcp", "MCP", "green")
    plugin_status.set_status("mcp", "MCP: news-digest", "red")
    assert plugin_status.get_all()["mcp"] == ("MCP: news-digest", "red")


def test_get_all_returns_copy():
    plugin_status.set_status("mcp", "MCP", "green")
    snapshot = plugin_status.get_all()
    snapshot["injected"] = ("X", "blue")
    assert "injected" not in plugin_status.get_all()


def test_clear_removes_all():
    plugin_status.set_status("mcp", "MCP", "green")
    plugin_status.clear()
    assert plugin_status.get_all() == {}
