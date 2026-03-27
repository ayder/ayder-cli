"""Tests for ChatView follow mode behavior."""

from unittest.mock import patch
from ayder_cli.tui.widgets import ChatView
from ayder_cli.tui.types import MessageType


class TestFollowMode:
    def test_follow_mode_default_true(self):
        view = ChatView()
        assert view._follow_mode is True

    def test_disable_follow_mode(self):
        view = ChatView()
        view.disable_follow_mode()
        assert view._follow_mode is False

    def test_enable_follow_mode(self):
        view = ChatView()
        view.disable_follow_mode()
        view.enable_follow_mode()
        assert view._follow_mode is True

    @patch.object(ChatView, "scroll_end")
    @patch.object(ChatView, "mount")
    def test_add_message_scrolls_when_follow_mode_on(self, mock_mount, mock_scroll):
        view = ChatView()
        view._follow_mode = True
        view.add_message("hello", MessageType.USER)
        mock_scroll.assert_called_with(animate=False)

    @patch.object(ChatView, "scroll_end")
    @patch.object(ChatView, "mount")
    def test_add_message_does_not_scroll_when_follow_mode_off(self, mock_mount, mock_scroll):
        view = ChatView()
        view._follow_mode = False
        view.add_message("hello", MessageType.USER)
        mock_scroll.assert_not_called()
