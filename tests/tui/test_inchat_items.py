"""Thinking, tool calls and agent runs are items in the chat, in order.

They are Statics built from Content (so the mouse can select their text) and
live in the ChatView next to the messages: a bordered thinking box that grows
with the reasoning up to 8 tail rows, one line per tool call or agent run until
Ctrl+O / Ctrl+G expand it to the full output.
"""

import re

import pytest
from textual.selection import Selection

from ayder_cli.core.config import Config
from ayder_cli.themes import get_theme
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.theme_manager import ThemeManager
from ayder_cli.tui.widgets import (
    AgentBox,
    AssistantReply,
    ChatView,
    ThinkingItem,
    ToolBox,
)

THEMES = ["ayder-dark", "claude"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def themed_app(monkeypatch):
    """Return a factory for an AyderApp under the named theme."""

    def make(theme_name: str = "ayder-dark") -> AyderApp:
        ThemeManager.reset_instance()
        ThemeManager(config=Config.model_validate({"ui": {"theme": theme_name}}))
        monkeypatch.setattr(AyderApp, "CSS", get_theme(theme_name).css)
        return AyderApp(model="test")

    yield make
    ThemeManager.reset_instance()


async def _settle(app, pilot, chat):
    chat.tick_live_items()  # the thinking box renders on the timer's tick
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


def _text(widget) -> str:
    """What the item shows, as plain text."""
    return str(widget.content)


def _lines(n: int, prefix: str = "line") -> str:
    return "\n".join(f"{prefix} {i}" for i in range(1, n + 1))


# -- Thinking box ------------------------------------------------------------


@pytest.mark.anyio
async def test_whitespace_only_reasoning_mounts_nothing(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("\n")
        chat.add_thinking_text("  \n ")
        chat.stop_thinking()
        await _settle(app, pilot, chat)
        assert not list(chat.query(ThinkingItem))
        assert chat.messages == []


@pytest.mark.anyio
async def test_first_non_blank_text_mounts_one_item(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("\n")
        await _settle(app, pilot, chat)
        assert not list(chat.query(ThinkingItem))
        chat.add_thinking_text("first thought")
        chat.add_thinking_text(" and more")
        await _settle(app, pilot, chat)
        (item,) = chat.query(ThinkingItem)
        assert "first thought and more" in _text(item)
        assert _text(item).startswith("∴ thinking… ")


@pytest.mark.anyio
@pytest.mark.parametrize("lines", [1, 2, 5, 8, 9, 20])
async def test_box_shows_min_lines_8_tail_rows_plus_a_header(themed_app, lines):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text(_lines(lines))
        await _settle(app, pilot, chat)
        (item,) = chat.query(ThinkingItem)
        rows = _text(item).splitlines()
        shown = min(lines, 8)
        assert len(rows) == 1 + shown
        assert rows[1:] == [f"line {i}" for i in range(lines - shown + 1, lines + 1)]
        assert item.region.height == 1 + shown + 2  # header, tail rows, the border


@pytest.mark.anyio
async def test_the_box_grows_with_the_text_up_to_8_rows(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("line 1")
        await _settle(app, pilot, chat)
        (item,) = chat.query(ThinkingItem)
        heights = [item.region.height]
        for i in range(2, 13):
            chat.add_thinking_text(f"\nline {i}")
            await _settle(app, pilot, chat)
            heights.append(item.region.height)
        assert heights == [4, 5, 6, 7, 8, 9, 10, 11, 11, 11, 11, 11]


@pytest.mark.anyio
async def test_stop_changes_only_the_header(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 60)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text(_lines(12))
        await _settle(app, pilot, chat)
        (item,) = chat.query(ThinkingItem)
        before = _text(item).splitlines()
        height = item.region.height
        assert before[0].startswith("∴ thinking… ")

        chat.stop_thinking()
        await _settle(app, pilot, chat)

        after = _text(item).splitlines()
        assert re.fullmatch(r"∴ thought for \d+s · Ctrl\+T to expand", after[0])
        assert after[1:] == before[1:]
        assert item.region.height == height


@pytest.mark.anyio
async def test_ctrl_t_swaps_every_box_between_the_tail_and_the_full_text(themed_app):
    app = themed_app()
    async with app.run_test(size=(100, 80)) as pilot:
        chat = app.query_one(ChatView)
        for _ in range(2):
            chat.start_thinking()
            chat.add_thinking_text(_lines(20))
            chat.stop_thinking()
        await _settle(app, pilot, chat)
        first, second = chat.query(ThinkingItem)
        assert len(_text(first).splitlines()) == 9

        assert chat.toggle_thinking_expanded() is True
        await _settle(app, pilot, chat)
        for item in (first, second):
            rows = _text(item).splitlines()
            assert rows[0].endswith("Ctrl+T to collapse")
            assert rows[1:] == [f"line {i}" for i in range(1, 21)]
            assert item.region.height == 1 + 20 + 2

        assert chat.toggle_thinking_expanded() is False
        await _settle(app, pilot, chat)
        for item in (first, second):
            assert len(_text(item).splitlines()) == 9
            assert item.region.height == 11


# -- Tool box ----------------------------------------------------------------


@pytest.mark.anyio
async def test_tool_call_is_one_line_running_then_ok_with_a_line_count(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "file_read", {"path": "a.py"})
        await _settle(app, pilot, chat)
        (box,) = chat.query(ToolBox)
        assert _text(box) == '● file_read … running {"path":"a.py"}'
        assert box.region.height == 1

        chat.tool_completed("c1", _lines(3))
        await _settle(app, pilot, chat)
        assert _text(box) == '● file_read ✓ ok {"path":"a.py"} · 3 lines'
        assert box.region.height == 1
        assert not box.has_class("-error")


@pytest.mark.anyio
async def test_a_result_starting_with_error_is_an_error(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "shell", {"command": "false"})
        chat.tool_completed("c1", "Error: exit status 1")
        await _settle(app, pilot, chat)
        (box,) = chat.query(ToolBox)
        assert "● shell ✗ error" in _text(box) and "· 1 line" in _text(box)
        assert box.has_class("-error")


@pytest.mark.anyio
async def test_a_second_start_with_the_same_id_updates_the_box_in_place(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "file_read", {})  # announced by name first
        chat.tool_started("c1", "file_read", {"path": "a.py"})  # then with its arguments
        await _settle(app, pilot, chat)
        (box,) = chat.query(ToolBox)
        assert '{"path":"a.py"}' in _text(box)
        assert len(chat.messages) == 1


@pytest.mark.anyio
async def test_args_give_way_to_a_narrow_chat(themed_app):
    app = themed_app()
    async with app.run_test(size=(50, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "file_read", {"path": "x" * 80})
        chat.tool_completed("c1", _lines(40))
        await _settle(app, pilot, chat)
        (box,) = chat.query(ToolBox)
        text = _text(box)
        assert text.startswith("● file_read ✓ ok ") and text.endswith(" · 40 lines")
        assert "…" in text and box.region.height == 1


@pytest.mark.anyio
async def test_ctrl_o_and_ctrl_g_expand_to_the_full_bordered_output(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 100)) as pilot:
        chat = app.query_one(ChatView)
        chat.tool_started("c1", "get_news", {"hours": 24})
        chat.tool_completed("c1", _lines(40))
        chat.agent_event(7, "reviewer", "tool_start", {"call_id": "a1"})
        chat.agent_completed(7, "reviewer", _lines(30, "finding"), "done")
        await _settle(app, pilot, chat)
        (tool,) = chat.query(ToolBox)
        (agent,) = chat.query(AgentBox)
        assert tool.region.height == agent.region.height == 1

        # Ctrl+G: agents only.
        assert chat.toggle_agents_expanded() is True
        await _settle(app, pilot, chat)
        assert agent.region.height == 1 + 30 + 2 and tool.region.height == 1

        # Ctrl+O: tools and agents, no cap on the output.
        assert chat.toggle_tools_expanded() is True
        await _settle(app, pilot, chat)
        rows = _text(tool).splitlines()
        assert rows[1:] == [f"line {i}" for i in range(1, 41)]
        assert tool.region.height == 1 + 40 + 2
        assert tool.has_class("-expanded") and agent.has_class("-expanded")

        # A second Ctrl+O collapses both again.
        assert chat.toggle_tools_expanded() is False
        await _settle(app, pilot, chat)
        assert tool.region.height == agent.region.height == 1


@pytest.mark.anyio
async def test_boxes_started_while_expanded_are_expanded(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 60)) as pilot:
        chat = app.query_one(ChatView)
        chat.toggle_tools_expanded()
        chat.tool_started("c1", "shell", {})
        chat.tool_completed("c1", _lines(3))
        await _settle(app, pilot, chat)
        (box,) = chat.query(ToolBox)
        assert box.has_class("-expanded") and box.region.height == 1 + 3 + 2


# -- Agent box ---------------------------------------------------------------


@pytest.mark.anyio
async def test_the_first_event_mounts_the_agent_box(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        assert not list(chat.query(AgentBox))
        chat.agent_event(7, "reviewer", "thinking_start")
        chat.agent_event(7, "reviewer", "thinking_stop")
        await _settle(app, pilot, chat)
        (box,) = chat.query(AgentBox)
        assert _text(box) == "● reviewer running 0s · 0 tools"


@pytest.mark.anyio
async def test_tool_start_events_count_the_agents_tools(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.agent_event(7, "reviewer", "tool_start", {"call_id": "a1", "name": "x"})
        await _settle(app, pilot, chat)
        (box,) = chat.query(AgentBox)
        assert _text(box).endswith("· 1 tool")
        for call_id in ("a1", "a2", "a3"):  # a1 again: counted once
            chat.agent_event(7, "reviewer", "tool_start", {"call_id": call_id, "name": "x"})
        chat.agent_event(7, "reviewer", "tools_cleanup")
        await _settle(app, pilot, chat)
        assert _text(box).endswith("· 3 tools")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,shown,error",
    [("done", "✓ done", False), ("error", "✗ failed", True), ("timeout", "✗ failed", True)],
)
async def test_a_finished_run_says_done_or_failed(themed_app, status, shown, error):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.agent_event(7, "reviewer", "thinking_start")
        chat.agent_completed(7, "reviewer", "all good", status)
        await _settle(app, pilot, chat)
        (box,) = chat.query(AgentBox)
        assert f"● reviewer {shown} " in _text(box)
        assert box.has_class("-error") is error


@pytest.mark.anyio
async def test_the_runs_assignment_label_is_shown(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.agent_event(7, "reviewer", "thinking_start", None, "fix the parser · T12")
        chat.agent_event(7, "reviewer", "tool_start", {"call_id": "a1"}, "ignored later label")
        await _settle(app, pilot, chat)
        (box,) = chat.query(AgentBox)
        assert "reviewer running" in _text(box) and "fix the parser · T12" in _text(box)
        assert "ignored later label" not in _text(box)  # the first label wins
        assert _text(box).endswith("· 1 tool")

        chat.agent_completed(7, "reviewer", "ok\nline two", "done")
        chat.toggle_agents_expanded()
        await _settle(app, pilot, chat)
        assert "fix the parser · T12" in _text(box).splitlines()[0]


# -- Common ------------------------------------------------------------------


@pytest.mark.anyio
async def test_items_mount_in_order_and_a_chunk_after_an_item_starts_a_new_reply(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 60)) as pilot:
        chat = app.query_one(ChatView)
        chat.add_user_message("go")
        chat.start_thinking()
        chat.add_thinking_text("hmm")
        chat.stop_thinking()
        chat.add_assistant_message("first chunk")
        chat.add_assistant_message(" more of the first")  # merges into the same reply
        chat.tool_started("c1", "shell", {})
        chat.tool_completed("c1", "ok")
        chat.add_assistant_message("second reply")
        chat.agent_event(7, "reviewer", "thinking_start")
        await _settle(app, pilot, chat)

        kinds = [type(w).__name__ for w in chat.children if w.id != "banner-spacer"]
        assert kinds[-6:] == [
            "Static", "ThinkingItem", "AssistantReply", "ToolBox", "AssistantReply", "AgentBox",
        ]
        first, second = chat.query(AssistantReply)
        assert "first chunk more of the first" in first.source
        assert second.source == "second reply"


@pytest.mark.anyio
async def test_clear_messages_drops_all_item_state(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("hmm")
        chat.tool_started("c1", "shell", {})
        chat.agent_event(7, "reviewer", "thinking_start")
        await _settle(app, pilot, chat)

        chat.clear_messages()
        await _settle(app, pilot, chat)

        assert not list(chat.query(ThinkingItem)) and not list(chat.query(ToolBox))
        assert not list(chat.query(AgentBox))
        assert chat.messages == [] and chat._message_widgets == []
        assert chat._tool_boxes == {} and chat._agent_boxes == {}
        assert chat._thinking_item is None and chat._thinking_pending == ""
        # and a fresh call with a reused id starts a new box
        chat.tool_started("c1", "shell", {})
        await _settle(app, pilot, chat)
        assert len(list(chat.query(ToolBox))) == 1


@pytest.mark.anyio
async def test_item_text_is_selectable(themed_app):
    app = themed_app()
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("the reasoning")
        chat.tool_started("c1", "file_read", {"path": "a.py"})
        chat.tool_completed("c1", _lines(3))
        chat.agent_event(7, "reviewer", "thinking_start")
        await _settle(app, pilot, chat)

        for widget in (*chat.query(ThinkingItem), *chat.query(ToolBox), *chat.query(AgentBox)):
            selected = widget.get_selection(Selection(None, None))
            assert selected is not None and selected[0] == _text(widget)

        # and with the mouse
        box = chat.query_one(ToolBox)
        await pilot.mouse_down(box, offset=(0, 0))
        await pilot.hover(box, offset=(12, 0))
        await pilot.mouse_up(box, offset=(12, 0))
        assert app.screen.get_selected_text().startswith("● file_read")


# -- CSS ---------------------------------------------------------------------


def _rule(css: str, selector: str) -> str:
    return css.split(selector, 1)[1].split("}", 1)[0]


@pytest.mark.parametrize("theme_name", THEMES)
def test_items_paint_no_background(theme_name):
    css = re.sub(r"/\*.*?\*/", "", get_theme(theme_name).css, flags=re.DOTALL)
    for selector in (
        "ChatView > .thinking-item {",
        "ChatView > .toolbox,\nChatView > .agentbox {",
    ):
        assert "background: transparent;" in _rule(css, selector), selector


def test_ayder_item_borders_are_literal_ansi_colours():
    css = re.sub(r"/\*.*?\*/", "", get_theme("ayder-dark").css, flags=re.DOTALL)
    for selector in (
        "ChatView > .thinking-item {",
        "ChatView > .toolbox.-expanded,\nChatView > .agentbox.-expanded {",
        "ChatView > .toolbox.-expanded.-error,\nChatView > .agentbox.-expanded.-error {",
    ):
        borders = re.findall(r"border:\s*([^;]+);", _rule(css, selector))
        assert borders, selector
        for value in borders:
            assert "$" not in value and "ansi_" in value, f"{selector}: border {value!r}"


@pytest.mark.anyio
@pytest.mark.parametrize("theme_name", THEMES)
async def test_rendered_items_have_a_transparent_background(themed_app, theme_name):
    app = themed_app(theme_name)
    async with app.run_test(size=(120, 40)) as pilot:
        chat = app.query_one(ChatView)
        chat.start_thinking()
        chat.add_thinking_text("hmm")
        chat.tool_started("c1", "shell", {})
        chat.agent_event(7, "reviewer", "thinking_start")
        await _settle(app, pilot, chat)
        for widget in (*chat.query(ThinkingItem), *chat.query(ToolBox), *chat.query(AgentBox)):
            assert widget.styles.background.a == 0, type(widget).__name__
