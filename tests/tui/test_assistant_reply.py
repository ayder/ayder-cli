"""Assistant replies can be selected with the mouse and copied with Ctrl+C,
stream correctly, keep today's vertical rhythm and keep their code highlighting.

Replies used to be rich.markdown renderables inside a Static. Textual extracts
a selection only from Text/Content visuals, so dragging over a reply selected
nothing and users had to hold Shift for the terminal's own selection. Replies
are now drawn with Textual's own Markdown widget (AssistantReply in widgets.py).

Code colours come from the Textual theme the user picks ([ui] palette, or
Ctrl+P > Theme for the session), never from a fixed scheme.

Every test drives the real app inline, as `ayder` runs it, under a pinned
theme (the default one would come from the user's config). Painted rows are
read from the screen compositor, a private Textual API used only here; it is
on the Textual internals watch.
"""

import random

import pytest

from ayder_cli.core.config import Config
from ayder_cli.themes import get_theme
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.theme_manager import ThemeManager
from ayder_cli.tui.widgets import ChatView, _SubmitTextArea

REPLY = """Here is the plan.

```python
def hello(name):
    s = 'single'
    return 42
```

| col a | col b |
|-------|-------|
| 1     | 2     |

Closing words."""

# Opens with a fence of several lines: the first chunk ends inside it.
STREAMED = """```python
def first():
    return 1

def second():
    return 2
```

Prose between the fences, long enough to be split across several chunks.

- one
- two

| a | b |
|---|---|
| 1 | 2 |
| 3 | 4 |

```
plain text block
```

The end."""

# Every token class textual 8.2.7's ANSI code themes misspell a colour for.
TOKEN_SAMPLES = """```python
class Foo:
    def __init__(self):
        s = 'single'
        x = $y
```

```html
<a href="x">t</a>
```"""

THEMES = ["ayder-dark", "ayder-light", "claude"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def inline_driver(monkeypatch):
    """Run the pilot the way the real app runs: inline."""
    from textual.drivers.headless_driver import HeadlessDriver

    monkeypatch.setattr(HeadlessDriver, "is_inline", property(lambda self: True))


@pytest.fixture
def themed_app(monkeypatch):
    """Return a factory for an AyderApp under the named theme."""

    def make(theme_name: str = "ayder-dark", palette: str | None = None) -> AyderApp:
        ui = {"theme": theme_name}
        if palette is not None:
            ui["palette"] = palette
        ThemeManager.reset_instance()
        ThemeManager(config=Config.model_validate({"ui": ui}))
        monkeypatch.setattr(AyderApp, "CSS", get_theme(theme_name).css)
        return AyderApp(model="test")

    yield make
    ThemeManager.reset_instance()


async def _settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


async def _reply(app, pilot, text=REPLY):
    """Add ``text`` as one assistant message; return the widget showing it."""
    chat_view = app.query_one("#chat-view", ChatView)
    chat_view.add_assistant_message(text)
    await _settle(app, pilot)
    return chat_view.children[-1]


def _painted_rows(app, widget) -> list[str]:
    """The text painted in ``widget``'s rows, stripped (all of it must be on screen)."""
    assert app.screen.region.contains_region(widget.region), "widget is not all on screen"
    strips = app.screen._compositor.render_strips()
    return [
        "".join(segment.text for segment in strips[y]).strip()
        for y in range(widget.region.y, widget.region.bottom)
    ]


def _row_segments(widget, needle):
    """The non-blank segments of the first painted row in ``widget`` (or one of
    its descendants) whose text contains ``needle``."""
    for node in [widget, *widget.query("*")]:
        for y in range(node.size.height):
            strip = node.render_line(y)
            if needle in "".join(segment.text for segment in strip):
                return [segment for segment in strip if segment.text.strip()]
    raise AssertionError(f"{needle!r} is not painted")


def _colour(segments, text):
    """The foreground colour of the segment whose text is ``text``."""
    for segment in segments:
        if segment.text.strip() == text:
            return segment.style.color if segment.style else None
    raise AssertionError(f"no segment {text!r} in {[s.text for s in segments]}")


async def _triple_click(app, pilot, widget, offset=(2, 0)):
    """Triple-click ``offset`` in ``widget`` the way a terminal does: the click
    goes to the innermost widget under the pointer (Pilot would otherwise send
    it to ``widget`` itself, whose select container is the whole chat)."""
    x, y = widget.region.x + offset[0], widget.region.y + offset[1]
    target, _ = app.get_widget_at(x, y)
    await pilot.triple_click(target, offset=(x - target.region.x, y - target.region.y))


def _palette_rgb(theme_name: str, variable: str = "text-accent") -> tuple[int, int, int]:
    """The RGB of a design variable of a built-in Textual theme."""
    from textual.color import Color
    from textual.theme import BUILTIN_THEMES

    variables = BUILTIN_THEMES[theme_name].to_color_system().generate()
    return Color.parse(variables[variable]).rgb


def _cancelled(chat_view) -> bool:
    return any(m["content"] == "Turn cancelled." for m in chat_view.messages)


# -- Selection and copy ---------------------------------------------------------


@pytest.mark.anyio
async def test_dragging_over_a_reply_selects_its_text(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot)

        await pilot.mouse_down(reply, offset=(0, 0))
        await pilot.hover(reply, offset=(12, 4))
        await pilot.mouse_up(reply, offset=(12, 4))

        selected = app.screen.get_selected_text()
        assert selected, f"nothing selected: {selected!r}"
        assert selected.startswith("Here is the plan.")
        assert "def hello(name):" in selected


@pytest.mark.anyio
async def test_triple_click_selects_the_whole_reply_and_nothing_else(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        app.query_one("#chat-view", ChatView).add_user_message("the question")
        reply = await _reply(app, pilot)

        await _triple_click(app, pilot, reply)

        selected = app.screen.get_selected_text() or ""
        for text in ("Here is the plan.", "return 42", "col b", "Closing words."):
            assert text in selected, f"{text!r} missing from {selected!r}"
        assert "the question" not in selected


@pytest.mark.anyio
async def test_ctrl_c_copies_the_selected_reply_text_and_does_not_cancel(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        reply = await _reply(app, pilot)
        await _triple_click(app, pilot, reply)
        app.query_one("#chat-input", _SubmitTextArea).focus()
        await pilot.pause()

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.clipboard.startswith("Here is the plan.")
        assert app.clipboard.endswith("Closing words.")
        assert not _cancelled(chat_view)


@pytest.mark.anyio
async def test_ctrl_c_cancels_when_nothing_is_selected(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        await _reply(app, pilot)
        app.query_one("#chat-input", _SubmitTextArea).focus()
        await pilot.pause()

        await pilot.press("ctrl+c")
        await pilot.pause()

        assert _cancelled(chat_view)


@pytest.mark.anyio
async def test_escape_clears_the_selection_so_ctrl_c_cancels_again(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        reply = await _reply(app, pilot)
        await _triple_click(app, pilot, reply)
        app.query_one("#chat-input", _SubmitTextArea).focus()
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert not app.screen.selections
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert _cancelled(chat_view)


# -- Code highlighting ----------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", THEMES)
async def test_fenced_code_is_highlighted_not_plain(themed_app, theme_name):
    app = themed_app(theme_name)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot)

        segments = _row_segments(reply, "def hello(name):")

        colours = {segment.style.color for segment in segments if segment.style}
        assert len(colours) >= 3, f"{theme_name}: code row has colours {colours}"


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", ["ayder-dark", "ayder-light"])
async def test_ayder_code_colours_come_from_the_terminal_palette(themed_app, theme_name):
    app = themed_app(theme_name)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot)

        segments = _row_segments(reply, "def hello(name):")

        kinds = {
            colour.type.name
            for segment in segments
            if segment.style
            for colour in (segment.style.color, segment.style.bgcolor)
            if colour is not None
        }
        assert "TRUECOLOR" not in kinds, f"{theme_name}: fixed RGB in the code row: {kinds}"


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", THEMES)
@pytest.mark.parametrize(
    ("needle", "token", "plain"),
    [
        ("__init__(self):", "__init__", "("),
        ("s = 'single'", "single", "="),
        ("x = $y", "$", "x"),
        ('href="x"', "href", "<"),
    ],
    ids=["magic-method", "single-quoted-string", "error", "attribute"],
)
async def test_every_token_class_is_coloured(themed_app, theme_name, needle, token, plain):
    app = themed_app(theme_name)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot, TOKEN_SAMPLES)

        segments = _row_segments(reply, needle)

        assert _colour(segments, token) != _colour(segments, plain), (
            f"{theme_name}: {token!r} is drawn like {plain!r}"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", THEMES)
async def test_language_is_the_first_word_of_the_info_string(themed_app, theme_name):
    app = themed_app(theme_name)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(
            app, pilot, '```python title="x.py"\ndef hello(name):\n    return name\n```'
        )

        segments = _row_segments(reply, "def hello(name):")

        assert len({s.style.color for s in segments if s.style}) >= 3


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", THEMES)
@pytest.mark.parametrize("info", ["", "foobarlang"], ids=["no-language", "unknown-language"])
async def test_fence_without_a_known_language_is_plain(themed_app, theme_name, info):
    app = themed_app(theme_name)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot, f"```{info}\ndef f():\n    return 1\n```")

        segments = _row_segments(reply, "def f():")

        colours = {segment.style.color for segment in segments if segment.style}
        assert len(colours) == 1, f"{theme_name}: plain fence has colours {colours}"


# -- Colour scheme: code colours come from the chosen Textual theme ------------


@pytest.mark.anyio
@pytest.mark.parametrize("palette", ["monokai", "dracula", "nord"])
async def test_code_colours_come_from_the_chosen_palette(themed_app, palette):
    app = themed_app("ayder", palette=palette)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        assert app.theme == palette
        reply = await _reply(app, pilot)

        keyword = _colour(_row_segments(reply, "def hello(name):"), "def")

        assert keyword.triplet == _palette_rgb(palette), f"{palette}: def is {keyword}"


@pytest.mark.anyio
async def test_switching_the_palette_rehighlights_code(themed_app):
    app = themed_app("ayder")
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot)

        def keyword():
            return _colour(_row_segments(reply, "def hello(name):"), "def")

        assert keyword().type.name == "STANDARD", "auto: the terminal's own ANSI colour"
        app.theme = "dracula"  # what Ctrl+P > Theme does
        await _settle(app, pilot)
        assert keyword().triplet == _palette_rgb("dracula")
        app.theme = "ayder-dark"
        await _settle(app, pilot)
        assert keyword().type.name == "STANDARD"


@pytest.mark.anyio
async def test_an_unknown_palette_falls_back_with_a_message(themed_app):
    app = themed_app("ayder", palette="no-such-theme")
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()

        assert app.theme == "ayder-dark"
        chat_view = app.query_one("#chat-view", ChatView)
        notices = [m["content"] for m in chat_view.messages if "no-such-theme" in m["content"]]
        assert len(notices) == 1, notices
        assert "ayder-dark" in notices[0]


# -- Layout -----------------------------------------------------------------------


RHYTHM = """# Title

First paragraph.

## Heading

Second paragraph.

- item

Last paragraph."""


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", ["ayder-dark", "claude"])
async def test_reply_has_one_blank_row_between_blocks_and_none_around(
    themed_app, theme_name
):
    app = themed_app(theme_name)
    async with app.run_test(size=(80, 60)) as pilot:
        await pilot.pause()
        reply = await _reply(app, pilot, RHYTHM)

        rows = _painted_rows(app, reply)

        bullets = "•▪‣⭑◦"
        rows = [row.lstrip(bullets).strip() for row in rows]
        assert rows == [
            "Title",
            "",
            "First paragraph.",
            "",
            "Heading",
            "",
            "Second paragraph.",
            "",
            "item",
            "",
            "Last paragraph.",
        ], f"{theme_name}: {rows}"


# -- Streaming ----------------------------------------------------------------------


def _chunks(text: str, how: str) -> list[str]:
    if how == "random":
        rnd = random.Random(7)
        sizes = []
        while sum(sizes) < len(text):
            sizes.append(rnd.randint(1, 60))
    else:
        sizes = [int(how)] * (len(text) // int(how) + 1)
    out, i = [], 0
    for size in sizes:
        out.append(text[i : i + size])
        i += size
    return [c for c in out if c]


@pytest.mark.anyio
@pytest.mark.parametrize("how", ["1", "7", "40", "random"])
@pytest.mark.parametrize("yield_between", [False, True], ids=["burst", "yielding"])
async def test_streamed_reply_paints_like_the_whole_reply(themed_app, how, yield_between):
    app = themed_app()
    async with app.run_test(size=(100, 90)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        whole = await _reply(app, pilot, STREAMED)
        chat_view.add_user_message("again")

        for chunk in _chunks(STREAMED, how):
            chat_view.add_assistant_message(chunk)
            if yield_between:
                await pilot.pause()
        await _settle(app, pilot)
        streamed = chat_view.children[-1]

        assert _painted_rows(app, streamed) == _painted_rows(app, whole)


@pytest.mark.anyio
async def test_tool_call_markup_that_streams_in_is_removed(themed_app):
    raw = 'Before.\n\n<tool_call>{"name": "read_file"}</tool_call>\n\nAfter.'
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        whole = await _reply(app, pilot, "Before.\n\nAfter.")
        chat_view.add_user_message("again")

        for ch in raw:
            chat_view.add_assistant_message(ch)
        await _settle(app, pilot)

        assert _painted_rows(app, chat_view.children[-1]) == _painted_rows(app, whole)
