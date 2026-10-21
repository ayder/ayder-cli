"""Only sandbox refusals are reported as security errors (audit P0-3).

UnicodeDecodeError, int() failures and other bad input are ValueErrors too;
before this fix every tool reported them as "Security Error". No network
(environment: local-faked).
"""

from pathlib import Path

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.core.skills import SkillScope
from ayder_cli.tools.builtins.filesystem import file_editor, read_file
from ayder_cli.tools.builtins.note_tool import note
from ayder_cli.tools.builtins.skill import skill
from ayder_cli.tools.builtins.task_tool import task
from ayder_cli.tools.execution import execute_tool
from ayder_cli.tools.hooks import HookManager


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


def _not_security(r):
    assert isinstance(r, ToolError), r
    assert r.category == "validation" and "Security" not in str(r), (r.category, str(r))


def _skill_read(tmp_path, path):
    skill_dir = tmp_path / ".ayder" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: X\n---\nBody", encoding="utf-8")
    scope = SkillScope(project_root=Path(tmp_path), enabled=None, messages=None)
    return skill(ProjectContext(str(tmp_path)), "read", skill_scope=scope, name="alpha", path=path)


def test_read_file_binary(ctx, tmp_path):
    """Baseline regression: 'Security Error: utf-8 codec can't decode'."""
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
    r = read_file(ctx, "a.png")
    _not_security(r)
    assert "binary" in str(r)


def test_read_file_bad_line_number(ctx, tmp_path):
    """Baseline regression: an int() failure."""
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    _not_security(read_file(ctx, "a.txt", start_line="abc"))


def test_file_editor_insert_into_binary(ctx, tmp_path):
    """Baseline regression."""
    (tmp_path / "a.bin").write_bytes(b"\xff\xfe\x00")
    _not_security(file_editor(ctx, "a.bin", "insert", content="x", line_number=1))


def test_task_bad_limit(ctx):
    """Baseline regression."""
    _not_security(task(ctx, action="list", limit="abc"))


def test_note_bad_limit(ctx):
    """Baseline regression."""
    _not_security(note(ctx, action="list", limit="abc"))


def test_skill_md_is_not_a_resource(tmp_path):
    """Baseline regression: a usage mistake, not a sandbox refusal."""
    _not_security(_skill_read(tmp_path, "SKILL.md"))


def test_null_byte_path(ctx):
    """Baseline regression: Path.resolve raises 'embedded null byte'."""
    _not_security(execute_tool("read_file", {"file_path": "a\x00b"}, read_file, HookManager(), ctx))


def test_outside_path_is_security(ctx):
    """Preservation."""
    assert read_file(ctx, "../x").category == "security"


def test_execute_tool_outside_is_security(ctx):
    """Preservation."""
    r = execute_tool("read_file", {"file_path": "/etc/passwd"}, read_file, HookManager(), ctx)
    assert r.category == "security"


def test_skill_absolute_path_is_security(tmp_path):
    """Preservation."""
    assert _skill_read(tmp_path, "/etc/passwd").category == "security"


def test_sandbox_error_is_a_value_error(ctx):
    """New interface: callers catching ValueError keep working."""
    from ayder_cli.core.context import PathOutsideSandboxError

    with pytest.raises(PathOutsideSandboxError):
        ctx.validate_path("/etc/passwd")
    assert issubclass(PathOutsideSandboxError, ValueError)
