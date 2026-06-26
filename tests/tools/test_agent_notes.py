"""Tests for write_agent_note — durable, deterministic agent deliverable notes."""

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.notes import write_agent_note


def test_writes_note_with_frontmatter_and_sections(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="reviewer", run_id=3, generation=1, status="done",
        task="Review the auth module", content="# Findings\nAll good.",
        timestamp="20260618-143022",
    )
    assert rel == ".ayder/notes/runs/20260618-143022-reviewer-run3.md"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'agent: "reviewer"' in text and "run_id: 3" in text and 'status: "done"' in text
    assert "tags: [agent-result]" in text
    assert "## Task\nReview the auth module" in text
    assert "## Result\n# Findings\nAll good." in text


def test_error_status_appends_error_section(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(
        ctx, agent_name="writer", run_id=1, generation=2, status="error",
        task="t", content="partial", timestamp="20260618-090000", error="boom",
    )
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert 'status: "error"' in text
    assert "## Error\nboom" in text


def test_same_run_does_not_overwrite(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    a = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                         task="t", content="FIRST", timestamp="20260618-120000")
    b = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                         task="t", content="SECOND", timestamp="20260618-120000")
    assert a != b
    assert (tmp_path / a).read_text().endswith("FIRST\n")
    assert (tmp_path / b).read_text().endswith("SECOND\n")


def test_frontmatter_escapes_unsafe_agent_name(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    rel = write_agent_note(ctx, agent_name='weird:\t"name"\ninjected: true',
                           run_id=1, generation=1, status="done",
                           task="t", content="c", timestamp="20260618-120000")
    frontmatter = (tmp_path / rel).read_text(encoding="utf-8").split("---", 2)[1]
    assert "\ninjected: true" not in frontmatter   # newline did not create a new key
    assert "\t" not in frontmatter                 # tab escaped, not embedded
    assert 'agent: "weird:' in frontmatter


def test_write_failure_returns_none(tmp_path, monkeypatch):
    ctx = ProjectContext(str(tmp_path))
    import ayder_cli.tools.builtins.notes as notes_mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(notes_mod, "_write_note", boom)
    rel = write_agent_note(ctx, agent_name="x", run_id=1, generation=1, status="done",
                           task="t", content="c", timestamp="20260618-120000")
    assert rel is None
