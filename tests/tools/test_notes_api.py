"""Tests for the programmatic notes API (spec 04 §8, AC8)."""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.notes import (
    delete_note_file,
    list_note_ids,
    mint_note,
    read_note_file,
    update_note_file,
    write_note_file,
)


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


def _path(ctx, slug):
    return ctx.root / ".ayder" / "notes" / f"{slug}.md"


class TestWrite:
    def test_exclusive_creates_with_frontmatter(self, ctx):
        slug = write_note_file(ctx, "Plan Add Auth", "the body")
        assert slug == "plan-add-auth"
        text = _path(ctx, "plan-add-auth").read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "title:" in text
        assert "date:" in text
        assert "the body" in text

    def test_exclusive_raises_on_collision(self, ctx):
        write_note_file(ctx, "dup", "first")
        with pytest.raises(FileExistsError):
            write_note_file(ctx, "dup", "second", exclusive=True)
        # original untouched
        assert "first" in _path(ctx, "dup").read_text()

    def test_tags_rendered(self, ctx):
        write_note_file(ctx, "tagged", "b", tags="bug, security")
        text = _path(ctx, "tagged").read_text()
        assert "tags: [bug, security]" in text

    def test_non_exclusive_suffixes(self, ctx):
        a = write_note_file(ctx, "log", "one", exclusive=False)
        b = write_note_file(ctx, "log", "two", exclusive=False)
        assert a == "log"
        assert b == "log-2"
        assert _path(ctx, "log").exists()
        assert _path(ctx, "log-2").exists()


class TestRead:
    def test_roundtrip_strips_frontmatter(self, ctx):
        write_note_file(ctx, "r", "hello body")
        body = read_note_file(ctx, "r")
        assert body == "hello body"
        assert "title:" not in body

    def test_absent_returns_none(self, ctx):
        assert read_note_file(ctx, "missing") is None

    def test_slug_normalization_roundtrip(self, ctx):
        write_note_file(ctx, "Agent Wander TASK-003", "incident")
        assert read_note_file(ctx, "agent-wander-task-003") == "incident"


class TestUpdate:
    def test_append_keeps_prior_and_dates_entry(self, ctx):
        write_note_file(ctx, "log", "entry-1")
        assert update_note_file(ctx, "log", "entry-2") is True
        body = read_note_file(ctx, "log")
        assert "entry-1" in body
        assert "entry-2" in body
        assert "## 2" in body  # dated "## YYYY-..." subheading present

    def test_replace_overwrites_body(self, ctx):
        write_note_file(ctx, "log", "entry-1")
        assert update_note_file(ctx, "log", "fresh", mode="replace") is True
        body = read_note_file(ctx, "log")
        assert body.strip() == "fresh"
        assert "entry-1" not in body

    def test_absent_returns_false(self, ctx):
        assert update_note_file(ctx, "nope", "x") is False


class TestListDelete:
    def test_list_sorted_with_prefix(self, ctx):
        write_note_file(ctx, "agent-wander-a", "x")
        write_note_file(ctx, "agent-wander-b", "x")
        write_note_file(ctx, "plan-z", "x")
        assert list_note_ids(ctx) == ["agent-wander-a", "agent-wander-b", "plan-z"]
        assert list_note_ids(ctx, prefix="agent-wander") == [
            "agent-wander-a",
            "agent-wander-b",
        ]

    def test_list_empty(self, ctx):
        assert list_note_ids(ctx) == []

    def test_delete_removes_and_absent_false(self, ctx):
        write_note_file(ctx, "d", "x")
        assert delete_note_file(ctx, "d") is True
        assert not _path(ctx, "d").exists()
        assert delete_note_file(ctx, "d") is False


class TestMint:
    def test_mint_returns_written_id_and_distinct_on_collision(self, ctx):
        first = mint_note(ctx, "coder-run1", "deliverable")
        second = mint_note(ctx, "coder-run1", "deliverable again")
        assert first == "coder-run1"
        assert second == "coder-run1-2"
        assert read_note_file(ctx, "coder-run1-2") == "deliverable again"
