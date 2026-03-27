"""Tests for paste collapsing in _SubmitTextArea."""

from ayder_cli.tui.widgets import _SubmitTextArea


class TestPasteCollapsing:
    def test_short_paste_not_collapsed(self):
        widget = _SubmitTextArea()
        text = "line1\nline2"
        assert widget._should_collapse_paste(text) is False

    def test_long_paste_collapsed(self):
        widget = _SubmitTextArea()
        text = "line1\nline2\nline3\nline4\nline5"
        assert widget._should_collapse_paste(text) is True

    def test_threshold_boundary_not_collapsed(self):
        widget = _SubmitTextArea()
        text = "line1\nline2\nline3"
        assert widget._should_collapse_paste(text) is False

    def test_single_line_not_collapsed(self):
        widget = _SubmitTextArea()
        text = "just one line"
        assert widget._should_collapse_paste(text) is False

    def test_store_pasted_content(self):
        widget = _SubmitTextArea()
        content = "a\nb\nc\nd\ne"
        widget._store_paste(content)
        assert widget._pasted_content == content

    def test_collapse_display_text(self):
        widget = _SubmitTextArea()
        text = "a\nb\nc\nd\ne"
        assert widget._collapse_display_text(text) == "[pasted: 5 lines]"

    def test_get_submit_value_returns_paste_when_stored(self):
        widget = _SubmitTextArea()
        pasted = "line1\nline2\nline3\nline4"
        widget._pasted_content = pasted
        assert widget._get_submit_value() == pasted

    def test_get_submit_value_returns_none_when_no_paste(self):
        widget = _SubmitTextArea()
        widget._pasted_content = None
        assert widget._get_submit_value() is None

    def test_clear_paste_resets_state(self):
        widget = _SubmitTextArea()
        widget._pasted_content = "some\npasted\ncontent\nhere\nnow"
        widget._clear_paste()
        assert widget._pasted_content is None


class TestPasteHistoryCollapsing:
    def test_collapse_display_counts_lines_correctly(self):
        widget = _SubmitTextArea()
        text = "\n".join(f"line {i}" for i in range(20))
        assert widget._collapse_display_text(text) == "[pasted: 20 lines]"

    def test_empty_paste_not_collapsed(self):
        widget = _SubmitTextArea()
        assert widget._should_collapse_paste("") is False

    def test_newlines_only_collapsed(self):
        widget = _SubmitTextArea()
        text = "\n\n\n\n"
        assert widget._should_collapse_paste(text) is True
