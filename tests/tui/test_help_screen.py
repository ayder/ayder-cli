"""Tests for the CLIHelpScreen modal."""

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
