"""Unit tests for the unified context tool."""

import json
from unittest.mock import MagicMock

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.context import context


@pytest.fixture
def project_ctx(tmp_path):
    return ProjectContext(tmp_path)


def test_dispatcher_rejects_unknown_action(project_ctx):
    result = context(project_ctx=project_ctx, action="nope")
    assert isinstance(result, ToolError)
    assert "unknown action" in str(result).lower()


def test_dispatcher_requires_action(project_ctx):
    result = context(project_ctx=project_ctx, action="")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_save_creates_file_in_context_dir(project_ctx):
    result = context(
        project_ctx=project_ctx,
        action="save",
        name="session",
        content="hello",
    )

    assert isinstance(result, ToolSuccess)
    target = project_ctx.root / ".ayder" / "context" / "session.json"
    assert target.exists()
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["content"] == "hello"
    assert saved["name"] == "session"
    assert "saved_at" in saved


def test_save_versions_existing_on_default_overwrite(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")

    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert json.loads((ctx_dir / "s.json").read_text(encoding="utf-8"))[
        "content"
    ] == "v2"

    versioned = [
        path for path in ctx_dir.iterdir() if path.name.startswith("s.") and path.name != "s.json"
    ]
    assert len(versioned) == 1
    assert json.loads(versioned[0].read_text(encoding="utf-8"))["content"] == "v1"


def test_save_with_overwrite_true_skips_versioning(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(
        project_ctx=project_ctx,
        action="save",
        name="s",
        content="v2",
        overwrite=True,
    )

    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert json.loads((ctx_dir / "s.json").read_text(encoding="utf-8"))[
        "content"
    ] == "v2"
    assert [path for path in ctx_dir.iterdir() if path.name != "s.json"] == []


def test_save_missing_name_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="save", content="x")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_save_missing_content_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="save", name="s")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


@pytest.mark.parametrize(
    "bad_name",
    ["..", "../escape", "a/b", "a\\b", ".hidden", "name with spaces", ""],
)
def test_save_rejects_unsafe_slot_names(project_ctx, bad_name):
    result = context(
        project_ctx=project_ctx,
        action="save",
        name=bad_name,
        content="x",
    )
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_save_versioning_handles_rapid_repeat_saves(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")
    context(project_ctx=project_ctx, action="save", name="s", content="v3")

    ctx_dir = project_ctx.root / ".ayder" / "context"
    versioned = sorted(path.name for path in ctx_dir.iterdir() if path.name != "s.json")
    assert len(versioned) == 2


def test_load_returns_content_string(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="payload")
    result = context(project_ctx=project_ctx, action="load", name="s")
    assert isinstance(result, ToolSuccess)
    assert str(result) == "payload"


def test_load_missing_name_returns_validation_error(project_ctx):
    result = context(project_ctx=project_ctx, action="load")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_load_rejects_unsafe_slot_names(project_ctx):
    result = context(project_ctx=project_ctx, action="load", name="../escape")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_load_missing_slot_lists_available_in_error(project_ctx):
    context(project_ctx=project_ctx, action="save", name="alpha", content="a")
    context(project_ctx=project_ctx, action="save", name="beta", content="b")

    result = context(project_ctx=project_ctx, action="load", name="gamma")

    assert isinstance(result, ToolError)
    message = str(result)
    assert "gamma" in message
    assert "alpha" in message
    assert "beta" in message


def test_load_missing_slot_no_contexts_error(project_ctx):
    result = context(project_ctx=project_ctx, action="load", name="any")
    assert isinstance(result, ToolError)
    assert "no saved contexts" in str(result).lower()


def test_list_empty_returns_empty_array(project_ctx):
    result = context(project_ctx=project_ctx, action="list")
    assert isinstance(result, ToolSuccess)
    assert json.loads(str(result)) == []


def test_list_returns_current_slots_with_metadata(project_ctx):
    context(project_ctx=project_ctx, action="save", name="alpha", content="a")
    context(project_ctx=project_ctx, action="save", name="beta", content="bb")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))

    assert sorted(entry["name"] for entry in entries) == ["alpha", "beta"]
    for entry in entries:
        assert "saved_at" in entry
        assert isinstance(entry["size_bytes"], int)


def test_list_excludes_versioned_files(project_ctx):
    context(project_ctx=project_ctx, action="save", name="s", content="v1")
    context(project_ctx=project_ctx, action="save", name="s", content="v2")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))

    assert len(entries) == 1
    assert entries[0]["name"] == "s"


def test_list_includes_current_slots_with_dots_in_name(project_ctx):
    context(project_ctx=project_ctx, action="save", name="project.v1", content="v1")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))

    assert [entry["name"] for entry in entries] == ["project.v1"]


def test_list_surfaces_unreadable_slots(project_ctx):
    """Corrupt JSON files in .ayder/context/ are surfaced in `list` with an
    `unreadable: True` flag rather than silently dropped."""
    context(project_ctx=project_ctx, action="save", name="good", content="payload")

    ctx_dir = project_ctx.root / ".ayder" / "context"
    (ctx_dir / "broken.json").write_text("{ this is not valid json", encoding="utf-8")

    result = context(project_ctx=project_ctx, action="list")
    entries = json.loads(str(result))

    by_name = {e["name"]: e for e in entries}
    assert "good" in by_name
    assert "unreadable" not in by_name["good"]
    assert "broken" in by_name
    assert by_name["broken"].get("unreadable") is True


def test_stats_returns_token_and_cache_fields(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    fake_mgr = MagicMock()
    fake_mgr.get_stats.return_value = ContextStats(
        total_tokens=1000,
        available_tokens=9000,
        utilization_percent=10.0,
        message_count=5,
        compaction_count=0,
        messages_compacted=0,
    )
    fake_mgr._cache_monitor.last_status = MagicMock(state="hot", hit_ratio=0.87)

    result = context(project_ctx=project_ctx, action="stats", context_manager=fake_mgr)
    payload = json.loads(str(result))

    assert payload["total_tokens"] == 1000
    assert payload["available_tokens"] == 9000
    assert payload["cache_state"] == "hot"
    assert payload["cache_hit_ratio"] == 0.87
    assert payload["saved_contexts_count"] == 0


def test_stats_cache_na_when_monitor_absent(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    fake_mgr = MagicMock(spec=["get_stats"])
    fake_mgr.get_stats.return_value = ContextStats(
        total_tokens=100,
        available_tokens=900,
        utilization_percent=10.0,
        message_count=1,
        compaction_count=0,
        messages_compacted=0,
    )

    result = context(project_ctx=project_ctx, action="stats", context_manager=fake_mgr)
    payload = json.loads(str(result))

    assert payload["cache_state"] == "n/a"
    assert payload["cache_hit_ratio"] is None


def test_stats_counts_saved_contexts(project_ctx):
    from ayder_cli.core.context_manager import ContextStats

    context(project_ctx=project_ctx, action="save", name="a", content="x")
    context(project_ctx=project_ctx, action="save", name="b", content="y")
    fake_mgr = MagicMock(spec=["get_stats"])
    fake_mgr.get_stats.return_value = ContextStats()

    result = context(project_ctx=project_ctx, action="stats", context_manager=fake_mgr)
    payload = json.loads(str(result))

    assert payload["saved_contexts_count"] == 2


def test_stats_no_context_manager_returns_error(project_ctx):
    result = context(project_ctx=project_ctx, action="stats")
    assert isinstance(result, ToolError)
    assert "context_manager" in str(result).lower()


def test_clear_creates_auto_compact_slot(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}]

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary text",
        app=fake_app,
    )

    assert isinstance(result, ToolSuccess)
    slots = list((project_ctx.root / ".ayder" / "context").glob("auto-compact-*.json"))
    assert len(slots) == 1
    payload = json.loads(slots[0].read_text(encoding="utf-8"))
    assert payload["content"] == "summary text"


def test_clear_sets_pending_compact_on_app(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}] * 5

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary",
        keep_last_n=2,
        app=fake_app,
    )

    assert isinstance(result, ToolSuccess)
    assert fake_app._pending_compact["keep_last_n"] == 2
    assert fake_app._pending_compact["summary_content"] == "summary"
    assert fake_app._pending_compact["summary_name"].startswith("auto-compact-")


def test_clear_uses_explicit_name_when_provided(project_ctx):
    fake_app = MagicMock(_pending_compact=None, messages=[])

    context(
        project_ctx=project_ctx,
        action="clear",
        name="my-checkpoint",
        content="summary",
        app=fake_app,
    )

    assert (project_ctx.root / ".ayder" / "context" / "my-checkpoint.json").exists()


def test_clear_requires_content(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None

    result = context(project_ctx=project_ctx, action="clear", app=fake_app)

    assert isinstance(result, ToolError)
    assert result.category == "validation"
    # No side effects: pending_compact stays unset, no slot was written.
    assert fake_app._pending_compact is None
    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert not ctx_dir.exists() or not any(ctx_dir.iterdir())


def test_clear_requires_app(project_ctx):
    result = context(project_ctx=project_ctx, action="clear", content="summary")
    assert isinstance(result, ToolError)
    assert "tui session" in str(result).lower() or "app" in str(result).lower()
    # No side effects: no slot file was written even though content was supplied.
    ctx_dir = project_ctx.root / ".ayder" / "context"
    assert not ctx_dir.exists() or not any(ctx_dir.iterdir())


def test_clear_writes_recovery_snapshot_with_live_messages(project_ctx):
    """`context(action='clear')` must auto-save the conversation to
    `latest-context-before-clear` BEFORE the deferred wipe so recovery is
    possible without relying on the summary content alone."""
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [
        {"role": "system", "content": "You are Claude"},
        {"role": "user", "content": "do the smoke test"},
        {"role": "assistant", "content": "ok starting"},
    ]

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="LLM-supplied summary",
        app=fake_app,
    )
    assert isinstance(result, ToolSuccess)
    payload = json.loads(str(result))
    assert payload["recovery_slot"] == "latest-context-before-clear"

    recovery_path = project_ctx.root / ".ayder" / "context" / "latest-context-before-clear.json"
    assert recovery_path.exists()
    saved = json.loads(recovery_path.read_text())["content"]
    snapshot = json.loads(saved)
    assert snapshot["message_count"] == 3
    roles = [m["role"] for m in snapshot["messages"]]
    assert roles == ["system", "user", "assistant"]
    assert "do the smoke test" in snapshot["messages"][1]["content"]


def test_clear_recovery_snapshot_overwrites_previous(project_ctx):
    """A second clear must overwrite the recovery slot, not version it."""
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "first"}]

    context(project_ctx=project_ctx, action="clear", content="s1", app=fake_app)

    fake_app.messages = [{"role": "user", "content": "second"}]
    context(project_ctx=project_ctx, action="clear", content="s2", app=fake_app)

    ctx_dir = project_ctx.root / ".ayder" / "context"
    # Exactly ONE recovery file — no versioned predecessor for the recovery slot.
    matches = list(ctx_dir.glob("latest-context-before-clear*"))
    assert len(matches) == 1
    snapshot = json.loads(json.loads(matches[0].read_text())["content"])
    assert snapshot["messages"][-1]["content"] == "second"


def test_clear_returns_projected_counts(project_ctx):
    fake_app = MagicMock()
    fake_app._pending_compact = None
    fake_app.messages = [{"role": "user", "content": "x"}] * 10

    result = context(
        project_ctx=project_ctx,
        action="clear",
        content="summary",
        keep_last_n=3,
        app=fake_app,
    )
    payload = json.loads(str(result))

    assert payload["messages_before"] == 10
    assert payload["kept_last_n"] == 3
    assert payload["saved_as"].startswith("auto-compact-")


def test_context_tool_is_registered():
    from ayder_cli.tools.definition import TOOL_DEFINITIONS

    names = [tool_def.name for tool_def in TOOL_DEFINITIONS]
    assert "context" in names
    assert "save_memory" not in names
    assert "load_memory" not in names
    assert "save_context_memory" not in names
    assert "load_context_memory" not in names


def test_context_tool_schema_has_all_actions():
    from ayder_cli.tools.definition import TOOL_DEFINITIONS

    tool_def = next(tool_def for tool_def in TOOL_DEFINITIONS if tool_def.name == "context")
    action_schema = tool_def.parameters["properties"]["action"]
    assert set(action_schema["enum"]) == {"save", "load", "list", "stats", "clear"}
    assert tool_def.parameters["required"] == ["action"]


def test_context_tool_executes_via_registry(tmp_path):
    from ayder_cli.tools.registry import create_default_registry

    project_ctx = ProjectContext(tmp_path)
    registry = create_default_registry(project_ctx)

    result = registry.execute(
        "context",
        {"action": "save", "name": "test", "content": "hello"},
    )

    assert isinstance(result, ToolSuccess)
    assert (tmp_path / ".ayder" / "context" / "test.json").exists()
