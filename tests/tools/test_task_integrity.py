"""Task files keep their title and Signature, and identifiers resolve to one
task or none (audit P0-1, P2-10).

No network (environment: local-faked).
"""

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.task_tool import task
from ayder_cli.tools.builtins.tasks import create_task, read_task, resolve_task_path


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


def _touch(tasks_dir, *names):
    for name in names:
        (tasks_dir / name).write_text(
            f"# {name}\n\n## Signature\n- **ID:** {name[:8]}\n- **Status:** pending\n",
            encoding="utf-8",
        )


@pytest.mark.parametrize("files,ident,expected", [
    (["TASK-002-x.md", "TASK-001-api-v2.md"], "v2", "TASK-001-api-v2.md"),
    (["TASK-002-other.md", "TASK-005-add-oauth2.md"], "add-oauth2", "TASK-005-add-oauth2.md"),
    (["TASK-015-x.md"], "5", None),
    (["TASK-002-probe-a.md", "TASK-003-probe-b.md"], "probe", None),
])
def test_identifier_resolves_to_one_task_or_none(ctx, tasks_dir, files, ident, expected):
    """Baseline regression: today each resolves to the wrong task."""
    _touch(tasks_dir, *files)
    path = resolve_task_path(ctx, ident)
    assert (path.name if path else None) == expected


def test_exact_slug_beats_substring(ctx, tasks_dir):
    """Baseline regression: today the first sorted match (add-auth) wins."""
    _touch(tasks_dir, "TASK-001-add-auth.md", "TASK-002-auth.md")
    assert resolve_task_path(ctx, "auth").name == "TASK-002-auth.md"


def test_ambiguous_identifier_names_the_matches(ctx, tasks_dir):
    """Baseline regression: today show returns TASK-002's content."""
    _touch(tasks_dir, "TASK-002-probe-a.md", "TASK-003-probe-b.md")
    r = task(ctx, action="show", identifier="probe")
    assert isinstance(r, ToolError) and r.category == "validation"
    assert "TASK-002, TASK-003" in str(r) and "use the ID" in str(r)


def test_read_task_ambiguous_is_none(ctx, tasks_dir):
    """Baseline regression: the agent harness must not dispatch on a guess."""
    _touch(tasks_dir, "TASK-002-probe-a.md", "TASK-003-probe-b.md")
    assert read_task(ctx, "probe") is None


@pytest.mark.parametrize("ident", ["3", "003", "TASK-003", "TASK-3", "task-003", " 3 ",
                                   "TASK-003-add-auth", "TASK-003-add-auth.md", "add-auth",
                                   "auth"])
def test_documented_forms_resolve(ctx, tasks_dir, ident):
    """Preservation."""
    _touch(tasks_dir, "TASK-003-add-auth.md")
    assert resolve_task_path(ctx, ident).name == "TASK-003-add-auth.md"
