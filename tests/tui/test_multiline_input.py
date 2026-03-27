"""Tests for smart up/down key behavior in CLIInputBar.

Up/Down should navigate command history ONLY when the cursor is at the
edge of the text (first line for Up, last line for Down). When editing
multiline text and the cursor is in the middle, Up/Down should move the
cursor within the text instead.
"""

from unittest.mock import MagicMock
from ayder_cli.tui.widgets import CLIInputBar, _SubmitTextArea


class TestSmartUpDown:
    def _make_input_bar(self) -> CLIInputBar:
        bar = CLIInputBar(commands=["/help", "/clear"])
        bar._history = ["old command 1", "old command 2"]
        bar._history_index = len(bar._history)
        return bar

    def _make_mock_event(self, key: str) -> MagicMock:
        event = MagicMock()
        event.key = key
        return event

    def test_up_navigates_history_when_input_empty(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = ""
        mock_input.cursor_location = (0, 0)
        bar._input = mock_input

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_up_navigates_history_when_cursor_on_first_line(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = "line1\nline2\nline3"
        mock_input.cursor_location = (0, 3)
        bar._input = mock_input

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_up_moves_cursor_when_not_on_first_line(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = "line1\nline2\nline3"
        mock_input.cursor_location = (1, 3)
        bar._input = mock_input

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_not_called()
        event.stop.assert_not_called()

    def test_down_navigates_history_when_input_empty(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = ""
        mock_input.cursor_location = (0, 0)
        mock_input.document = MagicMock()
        mock_input.document.line_count = 1
        bar._input = mock_input

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_down_navigates_history_when_cursor_on_last_line(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = "line1\nline2\nline3"
        mock_input.cursor_location = (2, 3)
        mock_input.document = MagicMock()
        mock_input.document.line_count = 3
        bar._input = mock_input

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_down_moves_cursor_when_not_on_last_line(self):
        bar = self._make_input_bar()
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = "line1\nline2\nline3"
        mock_input.cursor_location = (0, 3)
        mock_input.document = MagicMock()
        mock_input.document.line_count = 3
        bar._input = mock_input

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_not_called()
        event.stop.assert_not_called()

    def test_up_navigates_history_when_no_input_widget(self):
        bar = self._make_input_bar()
        bar._input = None

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_down_navigates_history_when_no_input_widget(self):
        bar = self._make_input_bar()
        bar._input = None

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()
