"""Tests for smart up/down key behavior in CLIInputBar (boundary delegation).

Up/Down navigate command history ONLY at the true *visual* edge of the input —
the first character for Up, the last for Down. The edge is detected via the
TextArea's own ``get_cursor_up_location``/``get_cursor_down_location``: when the
would-be location equals the current one, the cursor cannot move further and we
are at the edge. Otherwise Up/Down move the cursor within the text (including
across *soft-wrapped* visual rows of a single logical line).

These are fast unit tests of the delegation logic with a mocked input; the
wrap-aware end-to-end behaviour is covered by the Pilot tests in
``test_input_box.py``.
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

    def _mock_input(self, *, text: str, cursor, up=None, down=None) -> MagicMock:
        """Mock input where get_cursor_up/down_location return ``up``/``down``.

        Passing ``up=cursor`` (resp. ``down``) means "cannot move further" =
        at the visual edge.
        """
        mock_input = MagicMock(spec=_SubmitTextArea)
        mock_input.text = text
        mock_input.cursor_location = cursor
        mock_input.get_cursor_up_location.return_value = cursor if up is None else up
        mock_input.get_cursor_down_location.return_value = cursor if down is None else down
        return mock_input

    def test_up_navigates_history_when_input_empty(self):
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="", cursor=(0, 0))

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_up_navigates_history_at_visual_top(self):
        # Cursor cannot move up (would-be location == current) -> at the top edge.
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="line1\nline2", cursor=(0, 0), up=(0, 0))

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_up_moves_cursor_when_not_at_visual_top(self):
        # Cursor can still move up (e.g. mid-line or a lower wrapped row) -> no history.
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="line1\nline2", cursor=(0, 3), up=(0, 0))

        event = self._make_mock_event("up")
        bar.on_key(event)

        event.prevent_default.assert_not_called()
        event.stop.assert_not_called()

    def test_down_navigates_history_when_input_empty(self):
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="", cursor=(0, 0))

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_down_navigates_history_at_visual_bottom(self):
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="line1\nline2", cursor=(1, 5), down=(1, 5))

        event = self._make_mock_event("down")
        bar.on_key(event)

        event.prevent_default.assert_called_once()
        event.stop.assert_called_once()

    def test_down_moves_cursor_when_not_at_visual_bottom(self):
        bar = self._make_input_bar()
        bar._input = self._mock_input(text="line1\nline2", cursor=(0, 3), down=(1, 0))

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
