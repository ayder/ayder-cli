"""Toggle panels (tools / thinking / agents) open at the top of the TUI and
toggle silently.

* Toggling a panel prints no "... panel visible/hidden" chat message.
* ToolPanel, ThinkingPanel and AgentPanel are laid out above #chat-view, so a
  panel opens at the top and the chat output next to the input bar stays put.
* Each panel's separator border is on its bottom edge (between panel and chat).
* ChatView stays scrolled to the end after a panel opens above it.
* Each panel has a fixed height (tools 10%, agents 10%, thinking 30% of the
  screen): it takes that height as soon as it opens, whatever it holds, and its
  content scrolls inside it, so streaming content never resizes the chat.

The layout checks run the real app through Textual's Pilot because they depend
on the mounted widget order and computed geometry. The real app runs inline
(``app.run(inline=True)``), so the pilot is switched to inline mode as well.
"""

import re

import pytest

from ayder_cli.themes import list_themes
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.widgets import AgentPanel, ChatView, ThinkingPanel, ToolPanel

PANEL_IDS = ["tool-panel", "thinking-panel", "agent-panel"]
PANEL_CLASSES = {
    "tool-panel": ToolPanel,
    "thinking-panel": ThinkingPanel,
    "agent-panel": AgentPanel,
}
TOGGLE_ACTIONS = {
    "tool-panel": "action_toggle_tools",
    "thinking-panel": "action_toggle_thinking",
    "agent-panel": "action_toggle_agents",
}


PANEL_SHARE = {"tool-panel": 0.10, "agent-panel": 0.10, "thinking-panel": 0.30}
PANEL_HEIGHT_RULE = {
    "ToolPanel": ("tool-panel", "10%"),
    "AgentPanel": ("agent-panel", "10%"),
    "ThinkingPanel": ("thinking-panel", "30%"),
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def inline_driver(monkeypatch):
    """Run the pilot the way the real app runs: inline (Screen:inline applies)."""
    from textual.drivers.headless_driver import HeadlessDriver

    monkeypatch.setattr(HeadlessDriver, "is_inline", property(lambda self: True))


def _open(app, panel_id):
    getattr(app, TOGGLE_ACTIONS[panel_id])()


def _fill(app, panel_id, count=200):
    """Put `count` lines / items / entries into an open panel."""
    panel = app.query_one(f"#{panel_id}")
    if panel_id == "tool-panel":
        for i in range(count):
            panel.add_tool(f"call-{i}", "read_file", {"path": f"file_{i}.py"})
    elif panel_id == "agent-panel":
        for i in range(count):
            panel.add_agent(f"agent-{i}", i)
    else:
        panel.add_thinking("\n".join(f"thought line {i}" for i in range(count)))
        panel.flush()


def _system_message_count(chat_view: ChatView) -> int:
    return len(list(chat_view.query(".system-message")))


# -- Toggle messages are gone --------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_toggle_adds_no_chat_message(panel_id, monkeypatch):
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        panel = app.query_one(f"#{panel_id}")
        calls: list[str] = []
        monkeypatch.setattr(
            ChatView, "add_system_message", lambda self, content: calls.append(content)
        )
        before = _system_message_count(chat_view)

        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        assert panel.display is True
        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        assert panel.display is False

        assert calls == []
        assert _system_message_count(chat_view) == before


@pytest.mark.anyio
async def test_toggle_thinking_still_tracks_show_thinking():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_toggle_thinking()
        assert app._show_thinking is True
        app.action_toggle_thinking()
        assert app._show_thinking is False


# -- Panels sit above the chat view ---------------------------------------------


@pytest.mark.anyio
async def test_panels_come_before_chat_view_and_bottom_chrome_stays_last():
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = [child.id for child in app.screen.children]
        chat = ids.index("chat-view")
        for panel_id in PANEL_IDS:
            assert ids.index(panel_id) < chat, f"{panel_id} must precede #chat-view"
        assert chat < ids.index("activity-bar") < ids.index("input-bar") < ids.index(
            "status-bar"
        )


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_open_panel_is_rendered_above_chat_view(panel_id):
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        await pilot.pause()
        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        panel = app.query_one(f"#{panel_id}")
        chat_view = app.query_one("#chat-view", ChatView)
        assert panel.region.y < chat_view.region.y
        assert panel.region.bottom <= chat_view.region.y


# -- Separator border sits between panel and chat -------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_panel_border_is_on_the_bottom_edge(panel_id):
    app = AyderApp(model="test")
    async with app.run_test() as pilot:
        await pilot.pause()
        styles = app.query_one(f"#{panel_id}").styles
        assert styles.border_bottom[0] == "solid"
        assert not styles.border_top[0]


@pytest.mark.parametrize("theme", list_themes(), ids=lambda t: t.name)
@pytest.mark.parametrize("selector", ["ToolPanel", "AgentPanel", "ThinkingPanel"])
def test_theme_panel_rules_use_border_bottom(theme, selector):
    css = re.sub(r"/\*.*?\*/", "", theme.css, flags=re.DOTALL)
    match = re.search(rf"^{selector}\s*\{{(.*?)\}}", css, flags=re.DOTALL | re.MULTILINE)
    assert match, f"{theme.name}: no {selector} rule"
    body = match.group(1)
    assert "border-bottom:" in body
    assert "border-top" not in body


# -- No off-end frame is ever drawn while a panel opens or closes ----------------


def _spy_on_chat_draws(monkeypatch):
    """Record (scroll_y, max_scroll_y) for every ChatView frame while enabled."""
    draws: list[tuple[float, float]] = []
    recording = [False]
    original = ChatView.render_lines

    def spy(self, crop):
        if recording[0]:
            draws.append((self.scroll_y, self.max_scroll_y))
        return original(self, crop)

    monkeypatch.setattr(ChatView, "render_lines", spy)
    return draws, recording


async def _toggle_and_record(app, pilot, panel_id, draws, recording):
    draws.clear()
    recording[0] = True
    _open(app, panel_id)
    await pilot.pause()
    await pilot.pause()
    recording[0] = False
    assert draws, "the spy saw no frame; it would prove nothing"


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_chat_view_is_never_drawn_off_end_while_a_panel_toggles(
    panel_id, monkeypatch
):
    """The resize and the re-pin must land in the same frame: a frame drawn at
    the old scroll offset (then corrected on the next frame) shows as a jump.
    This also guards ChatView._size_updated, which leans on textual internals."""
    draws, recording = _spy_on_chat_draws(monkeypatch)

    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        for i in range(80):
            chat_view.add_system_message(f"line {i}")
        await pilot.pause()
        await pilot.pause()
        assert chat_view.scroll_y == chat_view.max_scroll_y

        for _ in ("open", "close"):
            await _toggle_and_record(app, pilot, panel_id, draws, recording)
            assert all(y == end for y, end in draws), draws


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_scrolled_up_chat_view_keeps_its_offset_on_every_draw(
    panel_id, monkeypatch
):
    """The re-pin must do nothing once the user has scrolled up."""
    draws, recording = _spy_on_chat_draws(monkeypatch)

    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        for i in range(80):
            chat_view.add_system_message(f"line {i}")
        await pilot.pause()
        await pilot.pause()
        chat_view.disable_follow_mode()
        chat_view.scroll_to(y=10, animate=False)
        await pilot.pause()
        assert chat_view.scroll_y == 10

        for _ in ("open", "close"):
            await _toggle_and_record(app, pilot, panel_id, draws, recording)
            assert all(y == 10 for y, _end in draws), draws


# -- The newest rows are PAINTED, not just scrolled to ---------------------------


def _newest_row_is_painted(chat_view: ChatView) -> bool:
    """True when the last message sits at the bottom of the chat as laid out by the
    compositor (widget.region comes from its map, not from scroll_y)."""
    last = [child for child in chat_view.children if child.display][-1]
    return last.region.bottom == chat_view.region.bottom


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_newest_rows_stay_painted_through_open_close_open_cycles(panel_id):
    """Each open after the first used to leave the compositor's placements at the
    old offset (the pin happened after they were computed), cutting off the newest
    rows although scroll_y said 'at the end'."""
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        for i in range(80):
            chat_view.add_system_message(f"line {i}")
        await pilot.pause()
        await pilot.pause()
        assert _newest_row_is_painted(chat_view)

        for cycle in range(1, 4):
            for step in ("open", "close"):
                _open(app, panel_id)
                await pilot.pause()
                await pilot.pause()
                assert chat_view.scroll_y == chat_view.max_scroll_y
                assert _newest_row_is_painted(chat_view), f"cycle {cycle} {step}"


# -- Chat stays pinned to the end when a panel opens ----------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_chat_view_stays_at_end_after_panel_opens(panel_id):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        for i in range(80):
            chat_view.add_system_message(f"line {i}")
        await pilot.pause()
        await pilot.pause()
        assert chat_view.max_scroll_y > 0
        assert chat_view.scroll_y == chat_view.max_scroll_y

        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        await pilot.pause()

        assert chat_view.scroll_y == chat_view.max_scroll_y

        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        await pilot.pause()

        assert chat_view.scroll_y == chat_view.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_chat_view_position_is_kept_when_user_scrolled_up(panel_id):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        for i in range(80):
            chat_view.add_system_message(f"line {i}")
        await pilot.pause()
        await pilot.pause()
        chat_view.disable_follow_mode()
        chat_view.scroll_to(y=10, animate=False)
        await pilot.pause()
        assert chat_view.scroll_y == 10

        getattr(app, TOGGLE_ACTIONS[panel_id])()
        await pilot.pause()
        await pilot.pause()

        assert chat_view.scroll_y == 10


# -- Fixed heights --------------------------------------------------------------


def _css_block(css: str, selector: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    match = re.search(rf"^{re.escape(selector)}\s*\{{(.*?)\}}", css, flags=re.DOTALL | re.MULTILINE)
    assert match, f"no {selector} rule"
    return match.group(1)


@pytest.mark.parametrize("theme", list_themes(), ids=lambda t: t.name)
@pytest.mark.parametrize("selector", list(PANEL_HEIGHT_RULE))
def test_theme_panel_rules_fix_the_height(theme, selector):
    panel_id, height = PANEL_HEIGHT_RULE[selector]
    body = _css_block(theme.css, selector)
    assert re.search(rf"(?<![-\w])height:\s*{re.escape(height)};", body)
    assert "height: auto" not in body
    assert "min-height" not in body
    assert "max-height" not in body
    # No vertical padding: at these heights every row not taken by the bottom
    # border should go to content.
    assert re.search(r"(?<![-\w])padding:\s*0 1;", body)
    # The #id rule is more specific: it must not re-introduce a size.
    id_body = _css_block(theme.css, f"#{panel_id}")
    assert "height" not in id_body


@pytest.mark.anyio
@pytest.mark.parametrize("filled", [False, True], ids=["empty", "filled"])
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_open_panel_has_its_fixed_share_of_the_screen(panel_id, filled):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert app.is_inline
        _open(app, panel_id)
        await pilot.pause()
        if filled:
            _fill(app, panel_id)
            await pilot.pause()
            await pilot.pause()
        expected = PANEL_SHARE[panel_id] * app.screen.size.height
        height = app.query_one(f"#{panel_id}").region.height
        assert abs(height - expected) <= 1, f"{panel_id}: {height} rows, expected ~{expected}"


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", PANEL_IDS)
async def test_chat_view_height_is_unchanged_while_content_streams_into_a_panel(panel_id):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        chat_view = app.query_one("#chat-view", ChatView)
        _open(app, panel_id)
        await pilot.pause()
        before = chat_view.region.height
        panel_before = app.query_one(f"#{panel_id}").region.height

        _fill(app, panel_id)
        await pilot.pause()
        await pilot.pause()

        assert chat_view.region.height == before
        assert app.query_one(f"#{panel_id}").region.height == panel_before


# -- Streamed content stays scrolled to the panel's own newest line -------------


async def _stream_and_settle(app, pilot, panel_id, count=200):
    panel = app.query_one(f"#{panel_id}")
    for i in range(count):
        if panel_id == "thinking-panel":
            panel.add_thinking(f"thought line {i}\n")
        elif panel_id == "tool-panel":
            panel.add_tool(f"call-{i}", "read_file", {"path": f"file_{i}.py"})
        else:
            panel.add_agent(f"agent-{i}", i)
        if i % 20 == 19:
            await pilot.pause()
    await pilot.pause()
    await pilot.pause()
    return panel


@pytest.mark.anyio
async def test_thinking_panel_follows_its_newest_line(monkeypatch):
    monkeypatch.setattr(ThinkingPanel, "RENDER_INTERVAL_S", 0)
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        _open(app, "thinking-panel")
        await pilot.pause()
        panel = await _stream_and_settle(app, pilot, "thinking-panel")
        assert panel.max_scroll_y > 0
        assert panel.scroll_y == panel.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", ["tool-panel", "agent-panel"])
async def test_tool_and_agent_panels_follow_their_newest_entry(panel_id):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        _open(app, panel_id)
        await pilot.pause()
        panel = await _stream_and_settle(app, pilot, panel_id)
        assert panel.max_scroll_y > 0
        assert panel.scroll_y == panel.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize("panel_id", ["tool-panel", "agent-panel"])
async def test_completing_an_entry_scrolls_the_panel_to_its_end(panel_id):
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        _open(app, panel_id)
        await pilot.pause()
        panel = await _stream_and_settle(app, pilot, panel_id, count=60)
        panel.scroll_home(animate=False)
        await pilot.pause()
        assert panel.scroll_y == 0 < panel.max_scroll_y

        if panel_id == "tool-panel":
            panel.complete_tool("call-0", "ok")
        else:
            panel.complete_agent(0, "done")
        await pilot.pause()
        await pilot.pause()

        assert panel.scroll_y == panel.max_scroll_y


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("size", "min_rows"), [((100, 40), 2), ((100, 24), 1)], ids=["100x40", "100x24"]
)
@pytest.mark.parametrize("panel_id", ["tool-panel", "agent-panel"])
async def test_small_panels_keep_rows_for_content(panel_id, size, min_rows):
    app = AyderApp(model="test")
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        _open(app, panel_id)
        await pilot.pause()
        panel = app.query_one(f"#{panel_id}")
        assert panel.content_region.height >= min_rows
