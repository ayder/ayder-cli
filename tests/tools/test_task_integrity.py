"""Task files keep their title and Signature, and identifiers resolve to one
task or none (audit P0-1, P2-10).

No network (environment: local-faked).
"""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess
from ayder_cli.tools.builtins.task_tool import task
from ayder_cli.tools.builtins.tasks import create_task


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


@pytest.fixture
def tasks_dir(tmp_path):
    d = tmp_path / ".ayder" / "tasks"
    d.mkdir(parents=True)
    return d


def _new(ctx, title, body):
    assert isinstance(task(ctx, action="create", title=title, body=body), ToolSuccess)


def _file(tasks_dir):
    return next(tasks_dir.glob("TASK-001-*.md")).read_text(encoding="utf-8")


def test_update_section_named_like_title_changes_only_that_section(ctx, tasks_dir):
    """Baseline regression: today the file becomes '## Notes\\n\\nreplaced'."""
    _new(ctx, "Notes", "## Goal\ngoal text\n\n## Notes\ninner")
    before = _file(tasks_dir)
    r = task(ctx, action="update", identifier="1", section="Notes", content="replaced")
    after = _file(tasks_dir)
    assert isinstance(r, ToolSuccess)
    assert after.splitlines()[0] == "# Notes"
    assert before.split("## Notes")[0] == after.split("## Notes")[0]
    assert after.rstrip().endswith("## Notes\n\nreplaced")


def test_update_missing_section_named_like_title_appends(ctx, tasks_dir):
    """Baseline regression: today the title is replaced and the Signature lost."""
    _new(ctx, "Goal", "## Files\nf")
    task(ctx, action="update", identifier="1", section="Goal", content="g")
    text = _file(tasks_dir)
    assert text.startswith("# Goal\n\n## Signature\n") and "- **Status:** pending" in text
    assert text.rstrip().endswith("## Goal\n\ng")


def test_show_section_named_like_title_returns_only_that_section(ctx, tasks_dir):
    """Baseline regression: today it returns the whole file."""
    _new(ctx, "Notes", "## Goal\ngoal text\n\n## Notes\ninner")
    out = str(task(ctx, action="show", identifier="1", section="Notes"))
    assert out.startswith("## Notes") and "inner" in out and "## Signature" not in out


def test_meta_only_on_task_titled_signature(ctx, tasks_dir):
    """Baseline regression: today it returns the whole file."""
    _new(ctx, "Signature", "## Goal\ng")
    out = str(task(ctx, action="show", identifier="1", meta_only=True))
    assert out.startswith("## Signature") and out.count("Signature") == 1
    assert "## Goal" not in out


def test_body_h1_is_not_a_section(ctx, tasks_dir):
    """New interface: a later H1 is never matched, and it ends the section before it."""
    _new(ctx, "T", "## Goal\ng\n\n# Appendix\na")
    assert "Section not found" in str(task(ctx, action="show", identifier="1", section="Appendix"))
    assert "Appendix" not in str(task(ctx, action="show", identifier="1", section="Goal"))


def test_legacy_task_update_and_status(ctx, tasks_dir):
    """Preservation: the legacy format (no ## Signature) still updates."""
    create_task(ctx, "Legacy", "old")
    task(ctx, action="update", identifier="1", section="Description", content="new")
    task(ctx, action="update_status", identifier="1", status="done")
    text = _file(tasks_dir)
    assert "new" in text and "old" not in text and "- **Status:** done" in text
