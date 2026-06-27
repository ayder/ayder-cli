"""Tests for TUI themes: registration, the ayder layout + ANSI/RGB palette axis,
CSS validity, config-driven selection, and render-level terminal passthrough."""

import pytest

from ayder_cli.core.config import Config
from ayder_cli.themes import get_theme, get_theme_names, list_themes
from ayder_cli.tui.theme_manager import (
    ThemeManager,
    get_theme_ansi_color,
    get_theme_palette,
    get_theme_textual_theme,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _design_tokens(palette: str = "ayder-dark") -> dict:
    """The Textual design-token variables a given palette generates (keys WITHOUT
    the ``$`` prefix, as ``Stylesheet.set_variables`` expects). The tokenised
    AYDER_CSS references these, so a standalone parse needs them supplied."""
    from textual.theme import BUILTIN_THEMES
    from ayder_cli.themes.ayder import AYDER_TEXTUAL_THEMES

    themes = {t.name: t for t in AYDER_TEXTUAL_THEMES}
    themes.update(BUILTIN_THEMES)
    return dict(themes[palette].to_color_system().generate())


# ── Registration ────────────────────────────────────────────────────────


def test_builtin_themes_present():
    names = set(get_theme_names())
    assert {"claude", "ayder", "ayder-dark", "ayder-light"} <= names


def test_ayder_variants_registered():
    for name in ("ayder-dark", "ayder-light", "ayder"):
        theme = get_theme(name)
        assert theme is not None
        assert theme.description
        assert theme.css.strip()


def test_ayder_alias_matches_dark():
    """'ayder' is a backwards-compatible alias for 'ayder-dark'."""
    ayder = get_theme("ayder")
    dark = get_theme("ayder-dark")
    assert ayder.css == dark.css
    assert ayder.textual_theme == dark.textual_theme == "ayder-dark"


def test_all_ayder_layouts_share_one_css():
    """The layout is a single tokenised CSS shared by every ayder variant; only
    the default palette (textual_theme) differs."""
    css = {get_theme(n).css for n in ("ayder", "ayder-dark", "ayder-light")}
    assert len(css) == 1


def test_ayder_variants_name_their_textual_theme():
    assert get_theme("ayder-dark").textual_theme == "ayder-dark"
    assert get_theme("ayder-light").textual_theme == "ayder-light"
    # claude is a plain RGB CSS theme — no Textual ANSI theme.
    assert get_theme("claude").textual_theme is None


def test_ansi_flags():
    assert get_theme("ayder-dark").ansi is True
    assert get_theme("ayder-light").ansi is True
    assert get_theme("ayder").ansi is True
    assert get_theme("claude").ansi is False


def test_ayder_textual_themes_are_ansi_passthrough():
    """The registered Textual palettes must be ansi=True with terminal-default
    surfaces so the user's own background/palette is used."""
    from ayder_cli.themes.ayder import AYDER_TEXTUAL_THEMES

    names = {t.name for t in AYDER_TEXTUAL_THEMES}
    assert names == {"ayder-dark", "ayder-light"}
    for t in AYDER_TEXTUAL_THEMES:
        assert t.ansi is True
        for surface in (t.background, t.surface, t.panel, t.foreground):
            assert surface == "ansi_default"


def test_ayder_palettes_resolve_signature_look():
    """Under the ANSI palette the design tokens must resolve to ayder's exact
    look: terminal-default bg/fg, the fixed #5eaff5 primary (separator/prompt),
    and the terminal grey for muted chrome."""
    from ayder_cli.themes.ayder import AYDER_DARK_TEXTUAL, AYDER_LIGHT_TEXTUAL

    for theme in (AYDER_DARK_TEXTUAL, AYDER_LIGHT_TEXTUAL):
        gen = theme.to_color_system().generate()
        assert gen["background"] == "ansi_default"
        assert gen["foreground"] == "ansi_default"
        assert gen["primary"].upper() == "#5EAFF5"
        assert gen["text-muted"] == "ansi_bright_black"


# ── 'ayder' look-and-feel invariants ────────────────────────────────────


def test_ayder_chrome_uses_palette_tokens():
    """The always-visible chrome is tokenised (so it adapts to any palette) and
    the separator follows the palette's primary — not a hard-coded fill."""
    css = get_theme("ayder-dark").css
    assert "background: $background;" in css
    assert "border-top: heavy $primary;" in css
    # No solid RGB fills (the 'claude' theme's navy palette) leak into ayder.
    for solid in ("#1a1a35", "#12122a", "#0d0d1a", "#0a0a18"):
        assert solid not in css, f"ayder should not paint solid fill {solid}"


def test_ayder_body_text_follows_palette_foreground():
    """Body/input text uses $foreground so it tracks the active palette (the
    terminal's own fg under the ANSI palette)."""
    css = get_theme("ayder-dark").css
    for block_anchor in (
        "ChatView .assistant-message {",
        "CLIInputBar #chat-input {",
        "ToolPanel .tool-item {",
    ):
        block = css.split(block_anchor, 1)[1].split("}", 1)[0]
        assert "color: $foreground;" in block, f"{block_anchor} not palette-fg"


def test_ayder_never_paints_a_fixed_background():
    """Every 'background:' value must be a design token ($background/$surface…),
    an ANSI token (ansi_*, used for the opaque modal/overlay boxes), or
    'transparent' — never a fixed #rrggbb that would hard-code a colour into the
    layout. The palette decides whether the token paints or passes through."""
    import re

    css = re.sub(r"/\*.*?\*/", "", get_theme("ayder-dark").css, flags=re.DOTALL)

    for match in re.finditer(r"\bbackground:\s*([^;]+);", css):
        value = match.group(1).strip()
        assert "#" not in value, f"background: {value!r} hard-codes a colour"
        assert (
            value.startswith("$")
            or value.startswith("ansi_")
            or value == "transparent"
        ), f"background: {value!r} is neither a token, ANSI, nor transparent"


def test_ayder_input_box_allows_many_lines():
    """The input box must grow to many lines (it was capped at ~5: the old
    max-height 8 bar minus the heavy border + padding)."""
    import re

    css = get_theme("ayder").css
    field = css.split("CLIInputBar #chat-input {", 1)[1].split("}", 1)[0]
    field_max = re.search(r"max-height:\s*(\d+);", field)
    assert field_max and int(field_max.group(1)) >= 15, "input field too short"

    bar = css.split("\nCLIInputBar {", 1)[1].split("}", 1)[0]
    bar_max = re.search(r"max-height:\s*(\d+);", bar)
    # The bar must be tall enough to contain the field plus its border/padding.
    assert bar_max and int(bar_max.group(1)) > int(field_max.group(1))


def test_ayder_borders_use_concrete_colors_not_auto_tokens():
    """Border colours must be concrete (a hard $primary or the literal ANSI
    grey) — never $text-muted, which is an auto-contrast colour that Textual
    rejects for borders under RGB palettes."""
    import re

    css = re.sub(r"/\*.*?\*/", "", get_theme("ayder-dark").css, flags=re.DOTALL)
    for match in re.finditer(r"\bborder(?:-top|-bottom)?:\s*([^;]+);", css):
        value = match.group(1).strip()
        assert "$text-muted" not in value, f"border uses auto colour: {value!r}"


# ── CSS validity (parses under Textual, for every palette) ──────────────


@pytest.mark.parametrize("theme", list_themes(), ids=lambda t: t.name)
@pytest.mark.parametrize("palette", ["ayder-dark", "ayder-light", "monokai", "dracula"])
def test_theme_css_parses(theme, palette):
    """Every registered theme's CSS must parse cleanly under Textual for both the
    ANSI palettes and arbitrary RGB palettes (the tokenised layout overlay)."""
    from textual.css.stylesheet import Stylesheet

    stylesheet = Stylesheet()
    stylesheet.set_variables(_design_tokens(palette))
    stylesheet.add_source(theme.css, read_from=None)
    stylesheet.parse()  # raises StylesheetParseError on invalid CSS


# ── Config-driven selection ─────────────────────────────────────────────


def test_config_default_theme_is_ayder():
    """Fresh installs default to the terminal-respecting ayder layout."""
    assert Config().theme == "ayder"


def test_config_default_palette_is_auto():
    assert Config().palette == "auto"


@pytest.mark.parametrize("name", ["ayder-dark", "ayder-light", "ayder", "claude"])
def test_config_ui_section_selects_theme(name):
    assert Config.model_validate({"ui": {"theme": name}}).theme == name


@pytest.mark.parametrize("palette", ["auto", "ansi-dark", "monokai", "dracula"])
def test_config_ui_section_selects_palette(palette):
    assert Config.model_validate({"ui": {"palette": palette}}).palette == palette


def test_config_ui_section_without_theme_keeps_default():
    assert Config.model_validate({"ui": {}}).theme == "ayder"


def test_config_ui_section_without_palette_keeps_auto():
    assert Config.model_validate({"ui": {"theme": "ayder"}}).palette == "auto"


def test_theme_manager_applies_configured_theme():
    ThemeManager.reset_instance()
    try:
        config = Config.model_validate({"ui": {"theme": "ayder-light"}})
        manager = ThemeManager(config=config)
        assert manager.current_theme.name == "ayder-light"
        assert manager.get_textual_theme() == "ayder-light"
    finally:
        ThemeManager.reset_instance()


def test_theme_manager_falls_back_for_unknown_theme():
    ThemeManager.reset_instance()
    try:
        config = Config.model_validate({"ui": {"theme": "does-not-exist"}})
        manager = ThemeManager(config=config)
        assert manager.current_theme.name == "ayder"
    finally:
        ThemeManager.reset_instance()


def test_theme_accessors_track_configured_theme():
    for name, ansi, textual in [
        ("ayder-dark", True, "ayder-dark"),
        ("ayder-light", True, "ayder-light"),
        ("claude", False, None),
    ]:
        ThemeManager.reset_instance()
        try:
            cfg = Config.model_validate({"ui": {"theme": name}})
            assert get_theme_ansi_color(cfg) is ansi
            assert get_theme_textual_theme(cfg) == textual
        finally:
            ThemeManager.reset_instance()


# ── Palette resolution (the [ui] palette axis) ──────────────────────────


@pytest.mark.parametrize(
    "theme,palette,expected",
    [
        # auto -> the layout theme's own default palette
        ("ayder", "auto", "ayder-dark"),
        ("ayder-dark", "auto", "ayder-dark"),
        ("ayder-light", "auto", "ayder-light"),
        # friendly ANSI names map onto the tuned ayder palettes
        ("ayder", "ansi-dark", "ayder-dark"),
        ("ayder", "ansi-light", "ayder-light"),
        # an explicit palette overrides the layout's default, even the light alias
        ("ayder-light", "ansi-dark", "ayder-dark"),
        # arbitrary RGB Textual themes pass through verbatim (overlay)
        ("ayder", "monokai", "monokai"),
        ("ayder-dark", "dracula", "dracula"),
        # claude is self-contained RGB: no palette, even if one is set
        ("claude", "auto", None),
        ("claude", "monokai", None),
    ],
)
def test_get_theme_palette_resolution(theme, palette, expected):
    ThemeManager.reset_instance()
    try:
        cfg = Config.model_validate({"ui": {"theme": theme, "palette": palette}})
        assert get_theme_palette(cfg) == expected
    finally:
        ThemeManager.reset_instance()


# ── Render-level checks (mount the real app) ────────────────────────────


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _rendered_bg_types(widget) -> set[str]:
    """The Rich color *types* actually rendered for a widget's first line
    (e.g. {'DEFAULT'} for terminal passthrough, {'TRUECOLOR'} for a fixed RGB
    fill). This inspects real render output, not the style token."""
    strip = widget.render_line(0)
    return {
        seg.style.bgcolor.type.name
        for seg in strip
        if seg.style and seg.style.bgcolor
    }


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", ["ayder-dark", "ayder-light"])
async def test_ayder_renders_with_terminal_passthrough(monkeypatch, theme_name):
    """Mount the real app with an ayder ANSI palette and confirm it selects the
    matching Textual theme, which renders every surface — including the
    TextArea input — with the terminal's own default background.

    The input-field assertion is the one that matters: under the default RGB
    theme the input renders a near-black RGB fill; only an ANSI theme makes it
    render the terminal default (DEFAULT)."""
    from ayder_cli.tui.app import AyderApp

    ThemeManager.reset_instance()
    ThemeManager(config=Config.model_validate({"ui": {"theme": theme_name}}))
    monkeypatch.setattr(AyderApp, "CSS", get_theme(theme_name).css)

    try:
        app = AyderApp(model="test")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.theme == theme_name
            assert app.native_ansi_color is True

            # Style tokens: ansi_default is Color(..., ansi=-1).
            assert app.screen.styles.background.ansi == -1
            assert app.query_one("#input-bar").styles.background.ansi == -1
            assert app.query_one("#status-bar").styles.background.ansi == -1

            # Rendered output: the input field shows the terminal's own
            # background (DEFAULT), never a fixed RGB fill (TRUECOLOR was the
            # near-black bug). A STANDARD ANSI cell for the block cursor is fine.
            input_bgs = _rendered_bg_types(app.query_one("#chat-input"))
            assert "TRUECOLOR" not in input_bgs, f"input has an RGB fill: {input_bgs}"
            assert "DEFAULT" in input_bgs, f"input not terminal-default: {input_bgs}"

            # The separator is a deliberate blue (the ANSI palette's #5eaff5
            # primary), not orange.
            from textual.color import Color

            edge_type, edge_color = app.query_one("#input-bar").styles.border_top
            assert edge_type == "heavy"
            assert edge_color == Color.parse("#5eaff5")
    finally:
        ThemeManager.reset_instance()


@pytest.mark.anyio
async def test_ayder_layout_overlays_rgb_palette(monkeypatch):
    """The ayder LAYOUT overlaid on an RGB palette ([ui] palette = monokai)
    adopts that palette: it switches App.theme to monokai, renders a fixed RGB
    background (TRUECOLOR) — deliberately NOT respecting the terminal — and the
    separator follows monokai's primary, all from the same tokenised CSS."""
    from textual.color import Color
    from textual.theme import BUILTIN_THEMES

    from ayder_cli.tui.app import AyderApp

    ThemeManager.reset_instance()
    ThemeManager(
        config=Config.model_validate({"ui": {"theme": "ayder", "palette": "monokai"}})
    )
    monkeypatch.setattr(AyderApp, "CSS", get_theme("ayder").css)

    monokai_primary = Color.parse(
        BUILTIN_THEMES["monokai"].to_color_system().generate()["primary"]
    )
    try:
        app = AyderApp(model="test")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.theme == "monokai"
            assert app.native_ansi_color is False

            # RGB palette paints its own background (the documented trade-off).
            input_bgs = _rendered_bg_types(app.query_one("#chat-input"))
            assert "TRUECOLOR" in input_bgs, f"monokai should paint RGB: {input_bgs}"

            # Separator follows monokai's primary, proving the tokenised overlay.
            _, edge_color = app.query_one("#input-bar").styles.border_top
            assert edge_color == monokai_primary
    finally:
        ThemeManager.reset_instance()


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", ["ayder-dark", "ayder-light"])
async def test_command_palette_opens_under_ansi_palette(monkeypatch, theme_name):
    """Ctrl+P (Textual's command palette, for live palette previewing) must open
    and render under the ANSI palette — where $surface/$panel are transparent —
    without the modal-transparency trap that forced our own modals to ansi_black.
    Textual's ansi-theme handling gives it an ANSI backdrop, not an empty box."""
    from textual.widgets import Input

    from ayder_cli.tui.app import AyderApp

    assert AyderApp.ENABLE_COMMAND_PALETTE is True

    ThemeManager.reset_instance()
    ThemeManager(config=Config.model_validate({"ui": {"theme": theme_name}}))
    monkeypatch.setattr(AyderApp, "CSS", get_theme(theme_name).css)

    try:
        app = AyderApp(model="test")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+p")
            await pilot.pause()

            from textual.command import CommandPalette

            assert isinstance(app.screen, CommandPalette)
            # The search input renders against an ANSI/terminal backdrop (DEFAULT
            # or a STANDARD ANSI cell), never a fixed RGB fill under the ANSI
            # palette — i.e. it is not an invisible transparent box.
            search = app.screen.query_one(Input)
            bgs = _rendered_bg_types(search)
            assert "TRUECOLOR" not in bgs, f"command palette has an RGB fill: {bgs}"
            assert bgs & {"DEFAULT", "STANDARD"}, f"palette not ANSI-backed: {bgs}"
    finally:
        ThemeManager.reset_instance()


@pytest.mark.anyio
async def test_claude_keeps_default_rgb_theme(monkeypatch):
    """The default claude theme must NOT switch to an ANSI theme, so its
    deliberate RGB look (and Textual's default RGB rendering) is preserved."""
    from ayder_cli.tui.app import AyderApp

    ThemeManager.reset_instance()
    ThemeManager(config=Config.model_validate({"ui": {"theme": "claude"}}))
    monkeypatch.setattr(AyderApp, "CSS", get_theme("claude").css)

    try:
        app = AyderApp(model="test")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.theme not in {"ayder-dark", "ayder-light"}
            assert app.native_ansi_color is False
    finally:
        ThemeManager.reset_instance()
