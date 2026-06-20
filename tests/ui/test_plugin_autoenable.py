"""Tests for auto-enabling installed-plugin capability tags at startup.

A freshly installed plugin (e.g. mcp-tool) should work without the user manually
enabling its tag via /plugin: its capability tags are merged into the effective
tool_tags at startup. Builtin/optional tags (background, http, ...) stay governed
by config; only installed-plugin tags are auto-enabled.
"""

from ayder_cli.tools.definition import ToolDefinition
from ayder_cli.tui.app import _enable_installed_plugin_tags


def _td(tags: tuple[str, ...]) -> ToolDefinition:
    return ToolDefinition(name="t", description="", parameters={}, tags=tags)


def test_adds_plugin_tag_to_restricted_tags():
    out = _enable_installed_plugin_tags(
        frozenset({"core", "metadata", "http"}), (_td(("mcp",)),), []
    )
    assert "mcp" in out
    assert {"core", "metadata", "http"} <= out


def test_includes_status_badge_keys_when_no_live_tools():
    # mcp installed but server unreachable: no mcp-tagged tool loaded, but a
    # status badge ("mcp") is registered -> still auto-enabled.
    out = _enable_installed_plugin_tags(frozenset({"core"}), (), ["mcp"])
    assert "mcp" in out


def test_noop_when_tags_none():
    # None = no tag filter = every tool already enabled.
    assert _enable_installed_plugin_tags(None, (_td(("mcp",)),), ["mcp"]) is None


def test_ignores_core_and_metadata():
    out = _enable_installed_plugin_tags(frozenset({"core"}), (), ["core", "metadata"])
    assert out == frozenset({"core"})


def test_returns_same_when_no_plugins():
    base = frozenset({"core", "metadata"})
    assert _enable_installed_plugin_tags(base, (), []) == base
