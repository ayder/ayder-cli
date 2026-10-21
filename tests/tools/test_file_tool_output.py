"""File tools report what they did, within a bounded size (audit P1-5, P2-2..P2-7).

No network (environment: local-faked).
"""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.tools.builtins.filesystem import file_editor, read_file


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


# --- file_editor reports what it did (P2-3..P2-6) ---


def test_insert_past_eof_reports_real_line(ctx, tmp_path):
    """Baseline regression: said 'at line 99' but appended at line 6."""
    _write(tmp_path, "f.txt", "a\nb\nc\nd\ne\n")
    out = str(file_editor(ctx, "f.txt", "insert", content="x", line_number=99))
    assert "at line 6" in out and "(the file had 5 lines)" in out


def test_insert_past_eof_after_unterminated_line(ctx, tmp_path):
    """Baseline regression: the inserted text was glued onto 'b'."""
    _write(tmp_path, "f.txt", "a\nb")
    file_editor(ctx, "f.txt", "insert", content="x", line_number=9)
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "a\nb\nx\n"


def test_replace_identical_strings(ctx, tmp_path):
    """Baseline regression: reported 'Successfully replaced 1 occurrence'."""
    _write(tmp_path, "f.txt", "a = 1\n")
    r = file_editor(ctx, "f.txt", "replace", old_string="a = 1", new_string="a = 1")
    _validation(r, "identical")
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "a = 1\n"


def test_dry_run_header_absolute(tmp_path):
    """Baseline regression: a scratch-dir file got 'a//private/...'."""
    root, scratch = tmp_path / "root", tmp_path / "scratch"
    root.mkdir()
    scratch.mkdir()
    ctx = ProjectContext(str(root), scratch_dir=scratch)
    target = scratch / "f.txt"
    target.write_text("old\n", encoding="utf-8")
    out = str(file_editor(ctx, str(target), "write", content="new\n", dry_run=True))
    assert f"--- {target.resolve()}" in out and "a//" not in out


def test_write_created(ctx, tmp_path):
    """Baseline regression: always said 'Successfully wrote to'."""
    out = str(file_editor(ctx, "new.txt", "write", content="a\nb\n"))
    assert "(created, 2 lines)" in out


def test_write_overwrote(ctx, tmp_path):
    """Baseline regression."""
    _write(tmp_path, "f.txt", "a\nb\nc\n")
    out = str(file_editor(ctx, "f.txt", "write", content="z\n"))
    assert "(overwrote, 3 → 1 lines)" in out


def test_insert_in_range_message(ctx, tmp_path):
    """Preservation."""
    _write(tmp_path, "f.txt", "a\nb\n")
    out = str(file_editor(ctx, "f.txt", "insert", content="x", line_number=2))
    assert "Successfully inserted content at line 2 in f.txt" in out


def test_dry_run_header_relative(ctx, tmp_path):
    """Preservation."""
    _write(tmp_path, "f.txt", "old\n")
    out = str(file_editor(ctx, "f.txt", "write", content="new\n", dry_run=True))
    assert "--- a/f.txt" in out and "+++ b/f.txt" in out
