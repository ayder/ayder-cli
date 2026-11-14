"""Tests for the CLIHelpScreen modal."""

import pytest
from textual.widgets import Static

from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.screens import CLIHelpScreen
from ayder_cli.tui.keybindings import KEYBINDING_REGISTRY


class TestHelpScreen:
    def test_can_instantiate(self):
        screen = CLIHelpScreen()
        assert screen is not None

    def test_builds_content_from_registry(self):
        screen = CLIHelpScreen()
        content = screen._build_help_text()
        assert "Navigation" in content
        assert "Chat" in content
        assert "Panels" in content
        assert "General" in content

    def test_content_includes_all_keys(self):
        screen = CLIHelpScreen()
        content = screen._build_help_text()
        for key, desc, _ in KEYBINDING_REGISTRY:
            assert key in content, f"Key {key} not in help text"
            assert desc in content, f"Description {desc} not in help text"

    def test_content_includes_esc_hint(self):
        screen = CLIHelpScreen()
        content = screen._build_help_text()
        assert "Esc" in content


SELECT_HINT = (
    "Drag to select text; Ctrl+C copies it if the terminal allows clipboard access."
    " Hold Shift (Option in iTerm2 and Terminal.app) for the terminal's own selection."
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_help_screen_tells_how_to_select_text_with_the_mouse():
    app = AyderApp(model="test")
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.push_screen(CLIHelpScreen())
        await pilot.pause()

        content = str(app.screen.query_one("#help-content", Static).content)

        assert content.count(SELECT_HINT) == 1
        assert SELECT_HINT.isascii()
