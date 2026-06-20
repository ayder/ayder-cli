"""Tests for the StatusBar plugin-status badges (e.g. the green MCP indicator)."""

from rich.text import Text

from ayder_cli.tui.widgets import StatusBar


def _styles(text: Text) -> list[str]:
    return [str(span.style) for span in text.spans]


def test_compose_yields_plugin_badges_label():
    bar = StatusBar()
    ids = [getattr(w, "id", None) for w in bar.compose()]
    assert "plugin-badges" in ids


def test_render_badges_empty_is_blank():
    rendered = StatusBar._render_badges({})
    assert rendered.plain == ""


def test_render_badges_green_mcp_with_server_name():
    rendered = StatusBar._render_badges({"mcp": ("MCP: news-digest", "green")})
    # The active server name is shown...
    assert "MCP: news-digest" in rendered.plain
    # ...in green.
    assert any("green" in s for s in _styles(rendered))


def test_render_badges_red_when_disconnected():
    rendered = StatusBar._render_badges({"mcp": ("MCP", "red")})
    assert "MCP" in rendered.plain
    assert any("red" in s for s in _styles(rendered))


def test_render_badges_multiple():
    rendered = StatusBar._render_badges(
        {"mcp": ("MCP", "green"), "db": ("DB", "yellow")}
    )
    assert "MCP" in rendered.plain
    assert "DB" in rendered.plain


def test_refresh_plugin_badges_is_callable():
    assert callable(getattr(StatusBar, "refresh_plugin_badges", None))


def test_render_badges_grey_when_tag_disabled():
    # enabled_tags given and "mcp" not in it -> the badge is greyed, not green.
    rendered = StatusBar._render_badges(
        {"mcp": ("MCP: news-digest", "green")}, frozenset({"core", "metadata"})
    )
    assert "MCP: news-digest" in rendered.plain
    styles = _styles(rendered)
    assert any("grey" in s for s in styles)
    assert not any("green" in s for s in styles)


def test_render_badges_green_when_tag_enabled():
    rendered = StatusBar._render_badges(
        {"mcp": ("MCP", "green")}, frozenset({"core", "mcp"})
    )
    assert any("green" in s for s in _styles(rendered))


def test_render_badges_no_filter_keeps_registered_color():
    # enabled_tags=None means "no tag filter / all enabled" -> keep the colour.
    rendered = StatusBar._render_badges({"mcp": ("MCP", "green")}, None)
    assert any("green" in s for s in _styles(rendered))
