"""The session scratch directory under /tmp/ayder-<uid> and its sandbox root.

Kind: new interface. Models put temporary files in /tmp by habit; ayder gives
each session its own directory there and lets the file tools use it, while
every other path outside the project stays refused.
"""

import os
import stat

import pytest

from ayder_cli.core import context
from ayder_cli.core.context import ProjectContext, new_scratch_dir
from ayder_cli.tools.builtins.filesystem import file_editor


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_session_dir_is_private_and_per_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    first = new_scratch_dir(project)
    second = new_scratch_dir(project)

    assert first is not None and second is not None
    assert first != second
    assert first.is_dir() and second.is_dir()
    assert first.parent == second.parent
    assert first.parent.parent == context.SCRATCH_BASE
    assert first.parent.name.startswith("proj-")
    assert _mode(first) == 0o700
    assert _mode(context.SCRATCH_BASE) == 0o700


def test_same_named_projects_do_not_share_a_folder(tmp_path):
    a = tmp_path / "a" / "proj"
    b = tmp_path / "b" / "proj"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    assert new_scratch_dir(a).parent != new_scratch_dir(b).parent


def test_agent_dir_is_inside_the_session_dir(tmp_path):
    session = new_scratch_dir(tmp_path)

    agent = new_scratch_dir(tmp_path, parent=session, label="agent-reviewer")

    assert agent is not None
    assert agent.parent == session
    assert agent.name.startswith("agent-reviewer-")
    assert _mode(agent) == 0o700


def test_a_symlinked_base_is_refused(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = tmp_path / "base-link"
    link.symlink_to(elsewhere)
    monkeypatch.setattr(context, "SCRATCH_BASE", link)

    assert new_scratch_dir(tmp_path) is None
    assert list(elsewhere.iterdir()) == []


def test_a_base_owned_by_someone_else_is_refused(tmp_path, monkeypatch):
    other_uid = os.getuid() + 1
    monkeypatch.setattr(context.os, "getuid", lambda: other_uid)

    assert new_scratch_dir(tmp_path) is None


def test_an_unwritable_base_gives_no_scratch_dir(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(context, "SCRATCH_BASE", blocker / "base")

    assert new_scratch_dir(tmp_path) is None


class TestSandbox:
    @pytest.fixture
    def ctx(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        return ProjectContext(str(project), scratch_dir=new_scratch_dir(project))

    def test_paths_in_the_scratch_dir_are_allowed(self, ctx):
        target = ctx.scratch_dir / "notes" / "out.txt"
        assert ctx.validate_path(str(target)) == target.resolve()

    def test_paths_outside_both_roots_are_refused(self, ctx, tmp_path):
        with pytest.raises(ValueError):
            ctx.validate_path(str(tmp_path / "other.txt"))

    def test_a_symlink_out_of_the_scratch_dir_is_refused(self, ctx, tmp_path):
        (ctx.scratch_dir / "escape").symlink_to(tmp_path)
        with pytest.raises(ValueError):
            ctx.validate_path(str(ctx.scratch_dir / "escape" / "x.txt"))

    def test_without_a_scratch_dir_only_the_root_is_allowed(self, tmp_path):
        ctx = ProjectContext(str(tmp_path / "proj"))
        assert ctx.scratch_dir is None
        with pytest.raises(ValueError):
            ctx.validate_path("/tmp/x.txt")

    def test_file_editor_writes_into_the_scratch_dir(self, ctx):
        target = ctx.scratch_dir / "probe.py"
        result = file_editor(ctx, str(target), "write", content="print(1)\n")
        assert "Error" not in str(result)
        assert target.read_text(encoding="utf-8") == "print(1)\n"


class TestReuseOnResume:
    """A resumed session keeps the scratch directory its history refers to.

    Kind: baseline regression unless a docstring says preservation. Live session
    (2026-11-25): after ``ayder --resume`` the file tools refused the directory the
    restored conversation had used all along, while bash still wrote there. The
    saved path comes from a session file, so only a directory ayder itself would
    have created for this project is taken back.
    """

    def test_this_projects_session_dir_is_reused(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        saved = new_scratch_dir(project)

        reused = context.reusable_scratch_dir(project, str(saved.resolve()))

        assert reused is not None
        assert reused.resolve() == saved.resolve()

    def test_another_projects_dir_is_not_reused(self, tmp_path):
        """Preservation: the saved path must belong to this project."""
        project, other = tmp_path / "proj", tmp_path / "other"
        project.mkdir()
        other.mkdir()

        assert context.reusable_scratch_dir(project, new_scratch_dir(other)) is None

    def test_a_dir_outside_the_scratch_base_is_not_reused(self, tmp_path):
        """Preservation: a session file cannot add an arbitrary directory to the sandbox."""
        project, elsewhere = tmp_path / "proj", tmp_path / "elsewhere"
        project.mkdir()
        elsewhere.mkdir()

        assert context.reusable_scratch_dir(project, elsewhere) is None

    def test_a_symlink_in_the_project_folder_is_not_reused(self, tmp_path):
        """Preservation: the saved entry must be a real directory, not a link out."""
        project, elsewhere = tmp_path / "proj", tmp_path / "elsewhere"
        project.mkdir()
        elsewhere.mkdir()
        link = new_scratch_dir(project).parent / "20261125-000000-linked"
        link.symlink_to(elsewhere)

        assert context.reusable_scratch_dir(project, link) is None

    def test_a_missing_dir_is_not_reused(self, tmp_path):
        """Preservation: /tmp may have been cleared since the session was saved."""
        project = tmp_path / "proj"
        project.mkdir()
        gone = new_scratch_dir(project)
        gone.rmdir()

        assert context.reusable_scratch_dir(project, gone) is None


def _runtime(tmp_path, monkeypatch, **kwargs):
    from unittest.mock import MagicMock

    from ayder_cli.application import runtime_factory
    from ayder_cli.core.config import Config

    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    return runtime_factory.create_runtime(config=Config(), project_root=str(tmp_path), **kwargs)


def test_a_resumed_runtime_writes_into_the_saved_scratch_dir(tmp_path, monkeypatch):
    """Baseline regression: file_editor answered "outside project root" for this path."""
    saved = _runtime(tmp_path, monkeypatch).project_ctx.scratch_dir

    resumed = _runtime(tmp_path, monkeypatch, resume_scratch_dir=str(saved))

    assert resumed.project_ctx.scratch_dir == saved
    assert f"Scratch directory: {saved}" in resumed.system_prompt
    result = resumed.tool_registry.execute(
        "file_editor",
        {"file_path": str(saved / "notes.txt"), "operation": "write", "content": "kept"},
    )
    assert "Successfully wrote" in result
    assert (saved / "notes.txt").read_text() == "kept"


def test_a_resume_whose_scratch_dir_is_gone_gets_a_new_one(tmp_path, monkeypatch):
    """Preservation: without a usable saved directory the session starts one, as before."""
    gone = _runtime(tmp_path, monkeypatch).project_ctx.scratch_dir
    gone.rmdir()

    resumed = _runtime(tmp_path, monkeypatch, resume_scratch_dir=str(gone))

    assert resumed.project_ctx.scratch_dir is not None
    assert resumed.project_ctx.scratch_dir != gone
    assert resumed.project_ctx.scratch_dir.is_dir()
