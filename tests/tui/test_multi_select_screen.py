"""Tests for CLIMultiSelectScreen widget."""

import pytest
from ayder_cli.tui.screens import CLIMultiSelectScreen


def test_multi_select_screen_init():
    items = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]
    selected = {"a", "c"}
    screen = CLIMultiSelectScreen(
        title="Test", items=items, selected=selected
    )
    assert screen.selected == {"a", "c"}
    assert screen.selected_index == 0


def test_multi_select_toggle():
    items = [("a", "Alpha"), ("b", "Beta")]
    selected = {"a"}
    screen = CLIMultiSelectScreen(
        title="Test", items=items, selected=selected
    )
    # Toggle 'a' off
    screen._toggle_current()
    assert "a" not in screen.selected
    # Toggle 'a' back on
    screen._toggle_current()
    assert "a" in screen.selected
