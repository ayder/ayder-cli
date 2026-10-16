"""Task identifiers and listings must stay inside ``.ayder/tasks`` (finding F1).

``resolve_task_path`` joined the identifier onto the project root and the tasks
dir, so an absolute or ``../`` identifier reached any file. The ``task`` tool is
a ``w`` tool, so ``update``/``update_status`` wrote outside the sandbox that
``file_editor`` enforces at the same tier. Listings read every ``*.md`` in the
tasks dir, following symlinks that point outside.
"""

from __future__ import annotations

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.tools.builtins.task_tool import task
from ayder_cli.tools.builtins.tasks import list_tasks, read_task, resolve_task_path

TASK_BODY = "# {title}\n\n## Signature\n- **ID:** TASK-{n:03d}\n- **Status:** pending\n"


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "project"
    tasks = root / ".ayder" / "tasks"
    tasks.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tasks / "TASK-001-add-auth.md").write_text(TASK_BODY.format(title="Add auth", n=1))
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    return ProjectContext(str(root)), root, tasks, outside


def test_absolute_identifier_outside_project_is_not_resolved(layout):
    ctx, _, _, outside = layout
    victim = outside / "secret.md"
    victim.write_text("secret")
    assert resolve_task_path(ctx, str(victim)) is None


def test_dotdot_identifier_is_not_resolved(layout):
    ctx, _, _, outside = layout
    (outside / "victim.md").write_text("victim")
    assert resolve_task_path(ctx, "../outside/victim.md") is None
    assert resolve_task_path(ctx, "../../../outside/victim.md") is None


def test_dotdot_identifier_does_not_fall_through_to_id_match(layout):
    """An escaping path that exists must not be re-read as id 1 -> TASK-001."""
    ctx, _, _, outside = layout
    (outside / "TASK-1").write_text("x")
    assert resolve_task_path(ctx, "../../../outside/TASK-1") is None


def test_project_file_outside_tasks_dir_is_not_resolved(layout):
    ctx, _, _, _ = layout
    assert resolve_task_path(ctx, "pyproject.toml") is None


def test_update_cannot_append_to_file_outside_tasks_dir(layout):
    ctx, _, _, outside = layout
    victim = outside / "victim.md"
    victim.write_text("original\n")
    result = task(
        ctx, action="update", identifier="../../../outside/victim.md",
        section="Injected", content="x",
    )
    assert isinstance(result, ToolError)
    assert victim.read_text() == "original\n"


def test_outward_task_file_symlink_is_not_resolved(layout):
    ctx, _, tasks, outside = layout
    victim = outside / "victim.md"
    victim.write_text("- **Status:** pending\n")
    (tasks / "TASK-002-evil.md").symlink_to(victim)
    assert resolve_task_path(ctx, "TASK-002-evil.md") is None
    assert resolve_task_path(ctx, "2") is None
    assert resolve_task_path(ctx, "evil") is None
    result = task(ctx, action="update_status", identifier="2", status="done")
    assert isinstance(result, ToolError)
    assert victim.read_text() == "- **Status:** pending\n"


def test_task_list_skips_outward_symlink_without_reading_it(layout, monkeypatch):
    ctx, _, tasks, outside = layout
    victim = outside / "victim.md"
    victim.write_text("# Leaked title\n- **Status:** pending\n")
    (tasks / "TASK-002-evil.md").symlink_to(victim)

    from pathlib import Path

    real_read = Path.read_text

    def guarded(self, *a, **k):
        assert self.resolve() != victim.resolve(), "listing read an outside file"
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", guarded)
    listed = task(ctx, action="list", status="all")
    table = list_tasks(ctx, format="table", status="all")
    assert "TASK-002" not in listed and "evil" not in listed
    assert "Leaked" not in table and "TASK-002" not in table
    assert "TASK-001" in listed and "TASK-001" in table


def test_symlinked_tasks_dir_returns_security_error(tmp_path):
    root = tmp_path / "project"
    (root / ".ayder").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "TASK-001-x.md").write_text(TASK_BODY.format(title="Outside", n=1))
    (root / ".ayder" / "tasks").symlink_to(outside, target_is_directory=True)
    ctx = ProjectContext(str(root))

    result = task(ctx, action="show", identifier="1")
    assert isinstance(result, ToolError)
    assert result.category == "security"
    listed = task(ctx, action="list", status="all")
    assert isinstance(listed, ToolError) and listed.category == "security"
    assert resolve_task_path(ctx, "1") is None
    assert read_task(ctx, "1") is None


def test_in_dir_symlink_keeps_its_own_name_and_id(layout):
    """Preservation: an allowed symlink inside the tasks dir keeps its name."""
    ctx, root, tasks, _ = layout
    real = tasks / "real-body.txt"
    real.write_text(TASK_BODY.format(title="Linked", n=3))
    (tasks / "TASK-003-linked.md").symlink_to(real)
    path = resolve_task_path(ctx, "3")
    assert path is not None and path.name == "TASK-003-linked.md"
    canonical, rel, _ = read_task(ctx, "3")
    assert canonical == "TASK-003"
    assert rel == ".ayder/tasks/TASK-003-linked.md"


@pytest.mark.parametrize(
    "identifier",
    [".ayder/tasks/TASK-001-add-auth.md", "TASK-001-add-auth.md", "001", "1",
     "TASK-001", "add-auth"],
)
def test_documented_identifier_forms_still_resolve(layout, identifier):
    ctx, _, tasks, _ = layout
    assert resolve_task_path(ctx, identifier) == tasks / "TASK-001-add-auth.md"
