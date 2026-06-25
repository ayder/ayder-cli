"""Tests for the consolidated note(action=...) tool (spec 04, AC1-AC7)."""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.note_tool import note

BUDGET = 8192


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


class TestCreate:
    def test_create_returns_confirmation_and_writes_file(self, ctx):
        result = note(ctx, "create", note_id="Plan Add Auth", content="body")
        assert isinstance(result, ToolSuccess)
        assert "plan-add-auth" in result
        assert len(result) <= 120
        path = ctx.root / ".ayder" / "notes" / "plan-add-auth.md"
        assert path.exists()
        assert "body" in path.read_text()

    def test_create_with_tags(self, ctx):
        note(ctx, "create", note_id="t", content="b", tags="bug,security")
        text = (ctx.root / ".ayder" / "notes" / "t.md").read_text()
        assert "tags: [bug, security]" in text

    def test_create_existing_fails_and_leaves_file_identical(self, ctx):
        note(ctx, "create", note_id="dup", content="first")
        path = ctx.root / ".ayder" / "notes" / "dup.md"
        before = path.read_bytes()
        result = note(ctx, "create", note_id="dup", content="second")
        assert isinstance(result, ToolError)
        assert "already exists" in result
        assert "read" in result and "update" in result
        assert path.read_bytes() == before

    def test_create_requires_note_id_and_content(self, ctx):
        assert isinstance(note(ctx, "create", content="x"), ToolError)
        assert isinstance(note(ctx, "create", note_id="x"), ToolError)


class TestRead:
    def test_read_full(self, ctx):
        note(ctx, "create", note_id="r", content="hello world")
        result = note(ctx, "read", note_id="r")
        assert isinstance(result, ToolSuccess)
        assert "hello world" in result
        assert "title:" not in result  # frontmatter stripped

    def test_read_not_found(self, ctx):
        assert isinstance(note(ctx, "read", note_id="missing"), ToolError)

    def test_read_continuation_offset(self, ctx):
        note(ctx, "create", note_id="big", content="x" * 20000)
        first = note(ctx, "read", note_id="big")
        assert len(first) <= 4096 + 80
        assert "more chars (use offset=4000)" in first
        second = note(ctx, "read", note_id="big", offset=4000)
        assert "more chars (use offset=8000)" in second

    def test_slug_normalization_roundtrip(self, ctx):
        note(ctx, "create", note_id="Agent Wander TASK-003", content="incident")
        result = note(ctx, "read", note_id="agent-wander-task-003")
        assert "incident" in result


class TestUpdate:
    def test_update_append_keeps_both(self, ctx):
        note(ctx, "create", note_id="log", content="entry-1")
        result = note(ctx, "update", note_id="log", content="entry-2")
        assert isinstance(result, ToolSuccess)
        assert "append" in result
        body = note(ctx, "read", note_id="log")
        assert "entry-1" in body and "entry-2" in body

    def test_update_replace_overwrites(self, ctx):
        note(ctx, "create", note_id="log", content="entry-1")
        note(ctx, "update", note_id="log", content="fresh", mode="replace")
        body = note(ctx, "read", note_id="log")
        assert "fresh" in body and "entry-1" not in body

    def test_update_absent_fails(self, ctx):
        result = note(ctx, "update", note_id="nope", content="x")
        assert isinstance(result, ToolError)
        assert "create" in result

    def test_update_invalid_mode(self, ctx):
        note(ctx, "create", note_id="m", content="x")
        assert isinstance(note(ctx, "update", note_id="m", content="y", mode="zap"), ToolError)


class TestListDelete:
    def test_list_empty(self, ctx):
        result = note(ctx, "list")
        assert isinstance(result, ToolSuccess)
        assert "No notes" in result

    def test_list_rows_and_footer(self, ctx):
        note(ctx, "create", note_id="plan-x", content="b")
        result = note(ctx, "list")
        assert "plan-x" in result
        assert "1 total" in result
        assert "showing 1-1" in result

    def test_list_pagination_and_prefix(self, ctx):
        for i in range(60):
            note(ctx, "create", note_id=f"wander-{i:03d}", content="b")
        note(ctx, "create", note_id="plan-z", content="b")
        page1 = note(ctx, "list")
        assert "61 total" in page1
        assert "showing 1-30" in page1
        assert "more (use offset=30)" in page1
        assert len(page1) < BUDGET
        filtered = note(ctx, "list", prefix="wander")
        assert "60 total" in filtered
        assert "plan-z" not in filtered

    def test_delete_removes_and_absent_fails(self, ctx):
        note(ctx, "create", note_id="d", content="b")
        result = note(ctx, "delete", note_id="d")
        assert isinstance(result, ToolSuccess)
        assert "deleted" in result
        assert isinstance(note(ctx, "delete", note_id="d"), ToolError)


class TestDispatch:
    def test_unknown_action(self, ctx):
        assert isinstance(note(ctx, "frobnicate"), ToolError)


class TestRegistration:
    def test_note_definition_is_discovered_and_exempt_from_truncation(self):
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        td = TOOL_DEFINITIONS_BY_NAME["note"]
        assert td.func_ref == "ayder_cli.tools.builtins.note_tool:note"
        assert td.permission == "w"
        assert td.max_result_chars == 0
        assert td.parameters["required"] == ["action"]
        assert "action" in td.parameters["properties"]


class TestBudget:
    def test_read_clamps_oversized_request(self, ctx):
        note(ctx, "create", note_id="huge", content="y" * 50000)
        result = note(ctx, "read", note_id="huge", max_chars=999999)
        assert len(result) <= BUDGET

    def test_list_clamps_oversized_request(self, ctx):
        for i in range(300):
            note(ctx, "create", note_id=f"n-{i:03d}", content="b")
        result = note(ctx, "list", limit=999999)
        assert len(result) <= BUDGET
