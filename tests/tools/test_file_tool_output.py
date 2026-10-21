"""File tools report what they did, within a bounded size (audit P1-5, P2-2..P2-7).

No network (environment: local-faked).
"""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.tools.builtins.filesystem import read_file


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


def _write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def _validation(r, needle):
    assert isinstance(r, ToolError) and r.category == "validation", r
    assert needle in str(r), str(r)


# --- read_file: per-line and per-page caps (P1-5) ---


def test_long_line_is_cut(ctx, tmp_path):
    """Baseline regression: a 30K one-line file came back verbatim."""
    _write(tmp_path, "min.js", "x" * 30000)
    out = str(read_file(ctx, "min.js"))
    assert len(out) < 3000
    assert "[+28000 chars]" in out


def test_page_char_budget(ctx, tmp_path):
    """Baseline regression: 60 lines of 2000 chars came back as one 120K page."""
    _write(tmp_path, "wide.txt", "".join("y" * 2000 + "\n" for _ in range(60)))
    out = str(read_file(ctx, "wide.txt"))
    assert "\n60: " not in out
    assert "start_line=" in out


# --- read_file: impossible ranges (P2-2) ---


def test_start_after_end(ctx, tmp_path):
    """Baseline regression: empty body and 'showing lines 4-3'."""
    _write(tmp_path, "f.txt", "a\nb\nc\nd\ne\n")
    _validation(read_file(ctx, "f.txt", start_line=4, end_line=3), "must be <= end_line")


def test_start_past_eof(ctx, tmp_path):
    """Baseline regression: empty body and 'COMPLETE … showing lines 50-49'."""
    _write(tmp_path, "f.txt", "a\nb\nc\nd\ne\n")
    _validation(read_file(ctx, "f.txt", start_line=50), "past the end of the file (5 lines)")


def test_start_below_one(ctx, tmp_path):
    """Baseline regression: lines were numbered from -5."""
    _write(tmp_path, "f.txt", "a\nb\n")
    _validation(read_file(ctx, "f.txt", start_line=-5), "start_line must be >= 1")


def test_explicit_range_unchanged(ctx, tmp_path):
    """Preservation."""
    _write(tmp_path, "f.txt", "a\nb\nc\nd\ne\n")
    assert str(read_file(ctx, "f.txt", start_line=2, end_line=3)).startswith("2: b\n3: c\n")


def test_empty_file(ctx, tmp_path):
    """Preservation: an empty file is complete, with or without a range."""
    _write(tmp_path, "e.txt", "")
    assert "COMPLETE: 0 lines" in str(read_file(ctx, "e.txt"))
    assert not isinstance(read_file(ctx, "e.txt", start_line=1), ToolError)
