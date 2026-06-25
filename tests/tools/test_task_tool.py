"""Tests for the consolidated ``task(action=...)`` tool (spec 01).

Covers AC1-AC7:
  AC1 next-ID allocation + O_EXCL retry
  AC2 list pagination + footer, bounded output
  AC3 show byte-offset continuation
  AC4 show section / meta_only projection
  AC5 update_status flips line; illegal transition leaves file byte-identical
  AC6 no action ever exceeds the 8192-char tool-result budget
  AC7 created files parse under the existing tasks.py readers
"""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins import task_tool
from ayder_cli.tools.builtins.task_tool import task
from ayder_cli.tools.builtins.tasks import (
    _extract_id,
    _parse_status,
    _parse_title,
    read_task,
)

BUDGET = 8192


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


@pytest.fixture
def tasks_dir(tmp_path):
    d = tmp_path / ".ayder" / "tasks"
    d.mkdir(parents=True)
    return d


def _write_raw(tasks_dir, name, *, status="pending", title="T", body=""):
    (tasks_dir / name).write_text(
        f"# {title}\n\n## Signature\n- **ID:** TASK-001\n- **Status:** {status}\n\n{body}\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
class TestCreate:
    def test_create_returns_compact_confirmation(self, ctx):
        result = task(ctx, "create", title="Add Auth")
        assert isinstance(result, ToolSuccess)
        assert "TASK-001" in result
        assert "agent/add-auth" in result
        assert "pending" in result
        assert len(result) <= 120

    def test_create_writes_canonical_signature(self, ctx):
        task(ctx, "create", title="Add Auth", body="## Goal\n\nDo the thing")
        path = ctx.root / ".ayder" / "tasks" / "TASK-001-add-auth.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# Add Auth")
        assert "## Signature" in text
        assert "- **ID:** TASK-001" in text
        assert "- **Status:** pending" in text
        assert "- **Branch:** agent/add-auth" in text
        assert "- **Created:**" in text
        assert "## Goal" in text
        assert "Do the thing" in text

    def test_create_custom_branch_and_status(self, ctx):
        result = task(
            ctx, "create", title="Fix Bug", branch="hotfix/x", status="in_progress"
        )
        assert "hotfix/x" in result
        assert "in_progress" in result
        path = ctx.root / ".ayder" / "tasks" / "TASK-001-fix-bug.md"
        text = path.read_text(encoding="utf-8")
        assert "- **Branch:** hotfix/x" in text
        assert "- **Status:** in_progress" in text

    def test_create_normalizes_dependencies(self, ctx):
        task(ctx, "create", title="Dep Task", dependencies="3, TASK-004 , 5")
        text = (ctx.root / ".ayder" / "tasks" / "TASK-001-dep-task.md").read_text()
        assert "- **Dependencies:** TASK-003, TASK-004, TASK-005" in text

    def test_create_default_dependencies_none(self, ctx):
        task(ctx, "create", title="No Deps")
        text = (ctx.root / ".ayder" / "tasks" / "TASK-001-no-deps.md").read_text()
        assert "- **Dependencies:** none" in text

    def test_create_strips_caller_signature_and_h1(self, ctx):
        body = (
            "# Bogus Title\n\n"
            "## Signature\n- **ID:** TASK-999\n- **Status:** done\n\n"
            "## Goal\n\nReal content"
        )
        task(ctx, "create", title="Clean", body=body)
        text = (ctx.root / ".ayder" / "tasks" / "TASK-001-clean.md").read_text()
        assert "Bogus Title" not in text
        assert "TASK-999" not in text
        assert text.count("## Signature") == 1
        assert "- **Status:** pending" in text
        assert "## Goal" in text
        assert "Real content" in text

    def test_create_rejects_empty_title(self, ctx):
        result = task(ctx, "create", title="   ")
        assert isinstance(result, ToolError)

    def test_create_rejects_invalid_status(self, ctx):
        result = task(ctx, "create", title="Bad", status="archived")
        assert isinstance(result, ToolError)

    def test_create_next_id_with_50_existing(self, ctx, tasks_dir):
        for i in range(1, 51):
            _write_raw(tasks_dir, f"TASK-{i:03d}-x{i}.md")
        result = task(ctx, "create", title="Fifty One")
        assert "TASK-051" in result

    def test_create_oexcl_retry_skips_collision(self, ctx, monkeypatch):
        # Force _next_id to hand back a stale id (1) twice, then 2.
        ids = iter([1, 1, 2])
        monkeypatch.setattr(task_tool, "_next_id", lambda _ctx: next(ids))

        first = task(ctx, "create", title="Same")
        assert "TASK-001" in first
        # Second create: _next_id->1 collides on the exact path, O_EXCL retries ->2.
        second = task(ctx, "create", title="Same")
        assert "TASK-002" in second
        assert (ctx.root / ".ayder" / "tasks" / "TASK-001-same.md").exists()
        assert (ctx.root / ".ayder" / "tasks" / "TASK-002-same.md").exists()


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
class TestList:
    def test_list_empty(self, ctx):
        result = task(ctx, "list")
        assert isinstance(result, ToolSuccess)
        assert "No tasks" in result

    def test_list_default_pending_only(self, ctx, tasks_dir):
        _write_raw(tasks_dir, "TASK-001-a.md", status="pending")
        _write_raw(tasks_dir, "TASK-002-b.md", status="done")
        result = task(ctx, "list")
        assert "TASK-001" in result
        assert "TASK-002" not in result

    def test_list_rows_and_footer(self, ctx, tasks_dir):
        _write_raw(tasks_dir, "TASK-001-add-auth.md", status="pending")
        result = task(ctx, "list")
        assert "TASK-001 [pending] add-auth" in result
        assert "1 total" in result
        assert "showing 1-1" in result

    def test_list_status_all_pagination(self, ctx, tasks_dir):
        for i in range(1, 201):
            _write_raw(tasks_dir, f"TASK-{i:03d}-t{i}.md", status="pending")
        page1 = task(ctx, "list", status="all")
        assert "200 total" in page1
        assert "showing 1-30" in page1
        assert len(page1) < BUDGET
        # next page
        page2 = task(ctx, "list", status="all", offset=30)
        assert "showing 31-60" in page2
        assert "TASK-031" in page2
        assert "TASK-030" not in page2

    def test_list_continuation_hint(self, ctx, tasks_dir):
        for i in range(1, 51):
            _write_raw(tasks_dir, f"TASK-{i:03d}-t{i}.md", status="pending")
        result = task(ctx, "list")
        assert "more (use offset=30)" in result


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #
class TestShow:
    def test_show_full(self, ctx):
        task(ctx, "create", title="Show Me", body="## Goal\n\nhello world")
        result = task(ctx, "show", identifier="1")
        assert isinstance(result, ToolSuccess)
        assert "Show Me" in result
        assert "hello world" in result

    def test_show_not_found(self, ctx, tasks_dir):
        result = task(ctx, "show", identifier="TASK-999")
        assert isinstance(result, ToolError)

    def test_show_continuation_offset(self, ctx):
        big = "## Goal\n\n" + ("x" * 20000)
        task(ctx, "create", title="Big", body=big)
        first = task(ctx, "show", identifier="1")
        assert len(first) <= 4096 + 80
        assert "more chars (use offset=4000)" in first
        # second page continues without overlap/loss
        second = task(ctx, "show", identifier="1", offset=4000)
        assert "more chars (use offset=8000)" in second

    def test_show_section_projection(self, ctx):
        body = "## Goal\n\nthe goal\n\n## Acceptance Criteria\n\n- one\n- two"
        task(ctx, "create", title="Sec", body=body)
        result = task(ctx, "show", identifier="1", section="Acceptance Criteria")
        assert "- one" in result
        assert "- two" in result
        assert "the goal" not in result

    def test_show_meta_only(self, ctx):
        task(ctx, "create", title="Meta", body="## Goal\n\nbody text")
        result = task(ctx, "show", identifier="1", meta_only=True)
        assert "## Signature" in result
        assert "- **ID:** TASK-001" in result
        assert "body text" not in result


# --------------------------------------------------------------------------- #
# status / update_status
# --------------------------------------------------------------------------- #
class TestStatus:
    def test_status_returns_current(self, ctx):
        task(ctx, "create", title="St", status="in_progress")
        result = task(ctx, "status", identifier="1")
        assert result == "TASK-001: in_progress"

    def test_status_not_found(self, ctx, tasks_dir):
        assert isinstance(task(ctx, "status", identifier="TASK-999"), ToolError)

    def test_update_status_flips_line(self, ctx):
        task(ctx, "create", title="Flip")
        result = task(ctx, "update_status", identifier="1", status="done")
        assert result == "TASK-001: pending → done"
        assert _parse_status(
            ctx.root / ".ayder" / "tasks" / "TASK-001-flip.md"
        ) == "done"

    def test_update_status_done_is_reopenable(self, ctx):
        task(ctx, "create", title="Reopen", status="done")
        result = task(ctx, "update_status", identifier="1", status="in_progress")
        assert "done → in_progress" in result

    def test_update_status_illegal_leaves_file_byte_identical(self, ctx):
        task(ctx, "create", title="Frozen")
        path = ctx.root / ".ayder" / "tasks" / "TASK-001-frozen.md"
        before = path.read_bytes()
        result = task(ctx, "update_status", identifier="1", status="archived")
        assert isinstance(result, ToolError)
        assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #
class TestUpdate:
    def test_update_replaces_section_preserving_signature(self, ctx):
        task(ctx, "create", title="Up", body="## Goal\n\nold goal\n\n## Notes\n\nkeep me")
        result = task(ctx, "update", identifier="1", section="Goal", content="new goal")
        assert isinstance(result, ToolSuccess)
        assert 'section "Goal"' in result
        text = (ctx.root / ".ayder" / "tasks" / "TASK-001-up.md").read_text()
        assert "new goal" in text
        assert "old goal" not in text
        assert "## Signature" in text
        assert "- **ID:** TASK-001" in text
        assert "keep me" in text

    def test_update_refuses_signature_section(self, ctx):
        task(ctx, "create", title="Guard")
        before = (ctx.root / ".ayder" / "tasks" / "TASK-001-guard.md").read_bytes()
        result = task(ctx, "update", identifier="1", section="Signature", content="x")
        assert isinstance(result, ToolError)
        assert (
            ctx.root / ".ayder" / "tasks" / "TASK-001-guard.md"
        ).read_bytes() == before

    def test_update_appends_missing_section(self, ctx):
        task(ctx, "create", title="App", body="## Goal\n\ng")
        task(ctx, "update", identifier="1", section="Risks", content="r1")
        text = (ctx.root / ".ayder" / "tasks" / "TASK-001-app.md").read_text()
        assert "## Risks" in text
        assert "r1" in text


# --------------------------------------------------------------------------- #
# dispatch / errors
# --------------------------------------------------------------------------- #
class TestDispatch:
    def test_unknown_action(self, ctx):
        assert isinstance(task(ctx, "frobnicate"), ToolError)


# --------------------------------------------------------------------------- #
# FR1 — registration via auto-discovery
# --------------------------------------------------------------------------- #
class TestRegistration:
    def test_task_definition_is_discovered_and_exempt_from_truncation(self):
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        td = TOOL_DEFINITIONS_BY_NAME["task"]
        assert td.func_ref == "ayder_cli.tools.builtins.task_tool:task"
        assert td.permission == "w"
        assert td.max_result_chars == 0
        assert td.parameters["required"] == ["action"]
        assert "action" in td.parameters["properties"]


# --------------------------------------------------------------------------- #
# AC6 — hard char-budget compliance
# --------------------------------------------------------------------------- #
class TestBudget:
    def test_show_clamps_oversized_request(self, ctx):
        task(ctx, "create", title="Huge", body="## Goal\n\n" + ("y" * 50000))
        result = task(ctx, "show", identifier="1", max_chars=999999)
        assert len(result) <= BUDGET

    def test_list_clamps_oversized_request(self, ctx, tasks_dir):
        for i in range(1, 301):
            _write_raw(tasks_dir, f"TASK-{i:03d}-task-{i}.md", status="pending")
        result = task(ctx, "list", status="all", limit=999999)
        assert len(result) <= BUDGET


# --------------------------------------------------------------------------- #
# AC7 — created files parse under existing readers
# --------------------------------------------------------------------------- #
class TestParseCompat:
    def test_created_file_parses_under_existing_readers(self, ctx):
        task(ctx, "create", title="Compat Task", body="## Goal\n\nwork")
        path = ctx.root / ".ayder" / "tasks" / "TASK-001-compat-task.md"
        assert _extract_id(path.name) == 1
        assert _parse_status(path) == "pending"
        assert _parse_title(path) == "Compat Task"
        read = read_task(ctx, "1")
        assert read is not None
        canonical_id, rel_path, content = read
        assert canonical_id == "TASK-001"
        assert rel_path == ".ayder/tasks/TASK-001-compat-task.md"
        assert "work" in content
