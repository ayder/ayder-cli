"""Context slots must stay inside ``.ayder/context`` (finding F6).

``_get_context_dir`` joined ``.ayder/context`` onto the root without resolving
it, and every slot target was used as found. A planted ``.ayder/context``
symlink, or a planted ``<slot>.json`` symlink, redirected reads and writes
outside the project. Named targets now fail with a security error; scans
(list, stats, the missing-slot fallback) omit outward entries unread.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.tools.builtins.context import context


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "project"
    ctx_dir = root / ".ayder" / "context"
    ctx_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    return ProjectContext(str(root)), root, ctx_dir, outside


def _victim(outside: Path, name: str = "victim.json") -> Path:
    victim = outside / name
    victim.write_text(json.dumps({"name": "victim", "content": "outside secret"}))
    return victim


def _guard_reads(monkeypatch, victim: Path):
    """Fail if anything reads or follow-stats the outside file.

    ``os.path.realpath`` is used because ``Path.resolve`` itself calls
    ``Path.stat``.
    """
    target = os.path.realpath(victim)
    real_read, real_stat = Path.read_text, Path.stat

    def read_text(self, *a, **k):
        assert os.path.realpath(self) != target, "read an outside file"
        return real_read(self, *a, **k)

    def stat(self, *a, **k):
        if k.get("follow_symlinks", True) and os.path.realpath(self) == target:
            raise AssertionError("stat-ed an outside file")
        return real_stat(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(Path, "stat", stat)


def test_outward_context_dir_refuses_save_and_load(tmp_path):
    root = tmp_path / "project"
    (root / ".ayder").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".ayder" / "context").symlink_to(outside, target_is_directory=True)
    ctx = ProjectContext(str(root))

    saved = context(ctx, action="save", name="slot", content="x")
    assert isinstance(saved, ToolError) and saved.category == "security"
    assert list(outside.iterdir()) == []
    loaded = context(ctx, action="load", name="slot")
    assert isinstance(loaded, ToolError) and loaded.category == "security"


def test_outward_slot_symlink_refuses_load(layout):
    ctx, _, ctx_dir, outside = layout
    victim = _victim(outside)
    (ctx_dir / "victim.json").symlink_to(victim)
    result = context(ctx, action="load", name="victim")
    assert isinstance(result, ToolError) and result.category == "security"
    assert "outside secret" not in result


def test_outward_slot_symlink_refuses_overwrite(layout):
    ctx, _, ctx_dir, outside = layout
    victim = _victim(outside)
    before = victim.read_bytes()
    (ctx_dir / "victim.json").symlink_to(victim)
    result = context(ctx, action="save", name="victim", content="new", overwrite=True)
    assert isinstance(result, ToolError) and result.category == "security"
    assert victim.read_bytes() == before


def test_outward_slot_symlink_is_not_renamed_on_versioned_save(layout):
    ctx, _, ctx_dir, outside = layout
    victim = _victim(outside)
    link = ctx_dir / "victim.json"
    link.symlink_to(victim)
    result = context(ctx, action="save", name="victim", content="new")
    assert isinstance(result, ToolError) and result.category == "security"
    assert link.is_symlink(), "the planted link must be left where it was"
    assert sorted(p.name for p in ctx_dir.iterdir()) == ["victim.json"]
    assert json.loads(victim.read_text())["content"] == "outside secret"


def test_list_and_stats_omit_outward_slot_without_reading_it(layout, monkeypatch):
    ctx, _, ctx_dir, outside = layout
    context(ctx, action="save", name="mine", content="inside")
    victim = _victim(outside)
    (ctx_dir / "victim.json").symlink_to(victim)
    _guard_reads(monkeypatch, victim)

    listed = json.loads(context(ctx, action="list"))
    assert [e["name"] for e in listed] == ["mine"]

    class _Stats:
        total_tokens = available_tokens = message_count = 0
        utilization_percent = 0.0
        compaction_count = messages_compacted = 0

    class _Manager:
        def get_stats(self):
            return _Stats()

    stats = json.loads(context(ctx, action="stats", context_manager=_Manager()))
    assert stats["saved_contexts_count"] == 1


def test_missing_slot_fallback_omits_outward_slot(layout, monkeypatch):
    ctx, _, ctx_dir, outside = layout
    context(ctx, action="save", name="mine", content="inside")
    victim = _victim(outside)
    (ctx_dir / "victim.json").symlink_to(victim)
    _guard_reads(monkeypatch, victim)

    result = context(ctx, action="load", name="absent")
    assert isinstance(result, ToolError)
    assert "mine" in result and "victim" not in result


def test_save_load_list_roundtrip_unchanged(layout):
    """Preservation: ordinary slots save, version, load and list as before."""
    ctx, _, ctx_dir, _ = layout
    assert not isinstance(context(ctx, action="save", name="a", content="one"), ToolError)
    assert not isinstance(context(ctx, action="save", name="a", content="two"), ToolError)
    assert context(ctx, action="load", name="a") == "two"
    versions = [p.name for p in ctx_dir.iterdir() if p.name.startswith("a.")]
    assert len(versions) == 2  # current + one versioned predecessor
    assert [e["name"] for e in json.loads(context(ctx, action="list"))] == ["a"]
