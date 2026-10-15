"""Notes must stay inside ``.ayder/notes`` (security audit of F6).

``_get_notes_dir`` joined ``.ayder/notes`` onto the root without resolving it,
and note targets were used as found, so a planted directory or file symlink
redirected note reads and writes outside the project. ``write_agent_note``
also appended ``runs/`` without checking it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.tools.builtins.note_tool import note
from ayder_cli.tools.builtins.notes import create_note, write_agent_note


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "project"
    notes = root / ".ayder" / "notes"
    notes.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    return ProjectContext(str(root)), root, notes, outside


def _victim(outside: Path) -> Path:
    victim = outside / "victim.md"
    victim.write_text("---\ntitle: v\n---\n\noutside secret\n")
    return victim


def _agent_note(ctx):
    return write_agent_note(
        ctx, agent_name="coder", run_id=1, generation=1, status="completed",
        task="t", content="c", timestamp="20261015-000000",
    )


def test_outward_notes_dir_returns_security_error(tmp_path):
    root = tmp_path / "project"
    (root / ".ayder").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".ayder" / "notes").symlink_to(outside, target_is_directory=True)
    ctx = ProjectContext(str(root))

    result = note(ctx, action="create", note_id="n", content="x")
    assert isinstance(result, ToolError) and result.category == "security"
    assert _agent_note(ctx) is None
    assert list(outside.iterdir()) == []


def test_note_update_through_outward_file_symlink_is_refused(layout):
    ctx, _, notes, outside = layout
    victim = _victim(outside)
    before = victim.read_bytes()
    (notes / "victim.md").symlink_to(victim)
    result = note(ctx, action="update", note_id="victim", content="x", mode="replace")
    assert isinstance(result, ToolError) and result.category == "security"
    assert victim.read_bytes() == before


def test_note_read_and_delete_through_outward_symlink_are_refused(layout):
    ctx, _, notes, outside = layout
    victim = _victim(outside)
    (notes / "victim.md").symlink_to(victim)
    read = note(ctx, action="read", note_id="victim")
    assert isinstance(read, ToolError) and read.category == "security"
    assert "outside secret" not in read
    deleted = note(ctx, action="delete", note_id="victim")
    assert isinstance(deleted, ToolError) and deleted.category == "security"
    assert (notes / "victim.md").is_symlink() and victim.exists()


def test_note_list_omits_outward_symlink(layout):
    ctx, _, notes, outside = layout
    assert not isinstance(note(ctx, action="create", note_id="mine", content="x"), ToolError)
    (notes / "victim.md").symlink_to(_victim(outside))
    listed = note(ctx, action="list")
    assert "mine" in listed and "victim" not in listed


def test_agent_note_through_outward_runs_symlink_returns_none(layout):
    ctx, _, notes, outside = layout
    (notes / "runs").symlink_to(outside, target_is_directory=True)
    assert _agent_note(ctx) is None
    assert list(outside.iterdir()) == []


def test_legacy_create_note_outward_dir_is_security_error(tmp_path):
    root = tmp_path / "project"
    (root / ".ayder").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".ayder" / "notes").symlink_to(outside, target_is_directory=True)
    result = create_note(ProjectContext(str(root)), title="t", content="x")
    assert isinstance(result, ToolError) and result.category == "security"
    assert list(outside.iterdir()) == []


def test_legacy_create_note_through_outward_file_symlink_is_refused(layout):
    ctx, _, notes, outside = layout
    victim = _victim(outside)
    before = victim.read_bytes()
    (notes / "victim.md").symlink_to(victim)
    result = create_note(ctx, title="victim", content="overwritten")
    assert isinstance(result, ToolError) and result.category == "security"
    assert victim.read_bytes() == before


def test_note_crud_roundtrip_unchanged(layout):
    """Preservation: create, read, update, list, delete and agent notes work."""
    ctx, _, notes, _ = layout
    assert not isinstance(note(ctx, action="create", note_id="a", content="one"), ToolError)
    assert note(ctx, action="read", note_id="a") == "one"
    assert not isinstance(
        note(ctx, action="update", note_id="a", content="two", mode="replace"), ToolError
    )
    assert note(ctx, action="read", note_id="a") == "two"
    assert "a" in note(ctx, action="list")
    assert not isinstance(note(ctx, action="delete", note_id="a"), ToolError)
    rel = _agent_note(ctx)
    assert rel is not None and rel.startswith(".ayder/notes/runs/")
    assert (notes / "runs").is_dir()
