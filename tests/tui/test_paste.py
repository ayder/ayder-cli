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

    def test_collapse_display_text(self):
        widget = _SubmitTextArea()
        text = "a\nb\nc\nd\ne"
        assert widget._collapse_display_text(text) == "[pasted: 5 lines]"


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


class TestPasteStorage:
    def test_pastes_start_empty(self):
        widget = _SubmitTextArea()
        assert widget._pastes == []

    def test_store_paste_appends_marker_and_content(self):
        widget = _SubmitTextArea()
        widget._store_paste("[pasted: 5 lines]", "a\nb\nc\nd\ne")
        assert widget._pastes == [("[pasted: 5 lines]", "a\nb\nc\nd\ne")]

    def test_store_paste_appends_in_order(self):
        widget = _SubmitTextArea()
        widget._store_paste("m1", "c1")
        widget._store_paste("m2", "c2")
        assert widget._pastes == [("m1", "c1"), ("m2", "c2")]

    def test_clear_paste_empties_list(self):
        widget = _SubmitTextArea()
        widget._store_paste("m", "c")
        widget._clear_paste()
        assert widget._pastes == []

    def test_remove_paste_removes_first_match(self):
        widget = _SubmitTextArea()
        widget._store_paste("m", "c1")
        widget._store_paste("m2", "c2")
        widget._remove_paste("m")
        assert widget._pastes == [("m2", "c2")]

    def test_remove_paste_no_match_is_noop(self):
        widget = _SubmitTextArea()
        widget._store_paste("m", "c")
        widget._remove_paste("missing")
        assert widget._pastes == [("m", "c")]


class TestPasteExpansion:
    def test_expand_with_no_pastes_returns_text_unchanged(self):
        widget = _SubmitTextArea()
        assert widget._expand_pastes("just typed text") == "just typed text"

    def test_expand_preserves_surrounding_text(self):
        """The reported bug: text typed around a paste must survive submit."""
        widget = _SubmitTextArea()
        content = "a\nb\nc\nd\ne"
        marker = widget._collapse_display_text(content)
        widget._store_paste(marker, content)
        displayed = f"hello {marker} world"
        assert widget._expand_pastes(displayed) == f"hello {content} world"

    def test_expand_multiple_distinct_pastes_in_place(self):
        widget = _SubmitTextArea()
        c1 = "\n".join(str(i) for i in range(5))
        c2 = "\n".join(str(i) for i in range(7))
        m1 = widget._collapse_display_text(c1)
        m2 = widget._collapse_display_text(c2)
        widget._store_paste(m1, c1)
        widget._store_paste(m2, c2)
        assert widget._expand_pastes(f"{m1} mid {m2}") == f"{c1} mid {c2}"

    def test_expand_identical_markers_resolve_in_insertion_order(self):
        widget = _SubmitTextArea()
        marker = "[pasted: 5 lines]"
        widget._store_paste(marker, "FIRST")
        widget._store_paste(marker, "SECOND")
        assert widget._expand_pastes(f"{marker} and {marker}") == "FIRST and SECOND"


class TestMarkerAtCursorEnd:
    def test_detects_marker_immediately_before_cursor(self):
        widget = _SubmitTextArea()
        marker = "[pasted: 5 lines]"
        widget._store_paste(marker, "content")
        assert widget._marker_at_cursor_end(f"hi {marker}") == marker

    def test_returns_none_when_no_marker_before_cursor(self):
        widget = _SubmitTextArea()
        widget._store_paste("[pasted: 5 lines]", "content")
        assert widget._marker_at_cursor_end("hi there") is None

    def test_returns_none_when_no_pastes_stored(self):
        widget = _SubmitTextArea()
        assert widget._marker_at_cursor_end("[pasted: 5 lines]") is None
