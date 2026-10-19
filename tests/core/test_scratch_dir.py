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
    monkeypatch.setattr(context.os, "getuid", lambda: os.getuid() + 1)

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
