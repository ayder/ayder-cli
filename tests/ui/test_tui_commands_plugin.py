"""Tests for /plugin command tag discovery.

The /plugin picker must surface installed plugins even when they currently
contribute no live tools (e.g. the mcp-tool plugin when its MCP server is
configured but unreachable). Such a plugin still publishes a status badge via
plugin_status, so its capability tag must appear in the toggle list.
"""

from ayder_cli.tools.definition import ToolDefinition
from ayder_cli.tui.commands import _available_plugin_tags


def _td(name: str, tags: tuple[str, ...]) -> ToolDefinition:
    return ToolDefinition(name=name, description="", parameters={}, tags=tags)


def test_includes_tag_from_live_tools():
    defs = (_td("get_recent_news", ("mcp",)),)
    assert "mcp" in _available_plugin_tags(defs, {})


def test_includes_inactive_plugin_via_status_badge():
    # No mcp-tagged tool loaded (server unreachable), but the plugin registered
    # a status badge — its capability tag must still appear so it's visible.
    defs = (_td("read_file", ("core",)),)
    tags = _available_plugin_tags(defs, {"mcp": ("MCP", "red")})
    assert "mcp" in tags


def test_excludes_core_and_metadata():
    defs = (_td("read_file", ("core", "metadata")),)
    assert _available_plugin_tags(defs, {}) == []


def test_sorted_and_deduplicated():
    defs = (_td("a", ("http",)), _td("b", ("mcp",)), _td("c", ("mcp",)))
    tags = _available_plugin_tags(defs, {"mcp": ("MCP", "green")})
    assert tags == ["http", "mcp"]
