"""The skill tool contract: list, load, read, unload; no TUI app needed."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.core.skills import SkillScope, active_skills
from ayder_cli.tools.builtins.skill import discover_skills, skill
from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME


def _ctx(tmp_path):
    return ProjectContext(str(tmp_path))


def _write_skill(tmp_path, name, content="---\ndescription: Does X\n---\n## Domain\nPython", files=None):
    skill_dir = tmp_path / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    for rel, text in (files or {}).items():
        (skill_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill_dir / rel).write_text(text, encoding="utf-8")
    return skill_dir


def _scope(tmp_path, messages=None, enabled=None):
    return SkillScope(project_root=Path(tmp_path), enabled=enabled, messages=messages)


def _run(tmp_path, action, messages=None, enabled=None, **kwargs):
    return skill(_ctx(tmp_path), action, skill_scope=_scope(tmp_path, messages, enabled), **kwargs)


def test_schema_actions_and_path():
    definition = TOOL_DEFINITIONS_BY_NAME["skill"]
    schema = definition.parameters
    assert schema["properties"]["action"]["enum"] == ["list", "load", "read", "unload"]
    assert "path" in schema["properties"]
    assert schema["required"] == ["action"]
    assert definition.max_result_chars == 0


def test_list_shows_layer_and_description(tmp_path):
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "list")
    assert result == "Available skills:\n- alpha (project): Does X"


def test_list_with_nothing_enabled(tmp_path):
    _write_skill(tmp_path, "alpha")
    assert _run(tmp_path, "list", enabled=frozenset()) == "No skills are enabled for this session."


def test_load_needs_no_app_and_returns_the_block(tmp_path):
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "load", name="alpha")
    assert isinstance(result, ToolSuccess)
    assert result.startswith("### SKILL LOADED: alpha\nSource: project (")
    assert result.endswith("## Domain\nPython\n\n### END SKILL: alpha")
    assert "description:" not in result


def test_load_requires_name(tmp_path):
    result = _run(tmp_path, "load")
    assert isinstance(result, ToolError)
    assert "required" in result


def test_load_unknown_lists_enabled(tmp_path):
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "load", name="missing")
    assert isinstance(result, ToolError)
    assert "Unknown or disabled skill: 'missing'" in result
    assert "Enabled: alpha" in result


def test_load_disabled_is_refused(tmp_path):
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "load", name="alpha", enabled=frozenset({"other"}))
    assert isinstance(result, ToolError)
    assert "No skills are enabled." in result


def test_load_empty_skill_is_refused(tmp_path):
    _write_skill(tmp_path, "empty", "")
    result = _run(tmp_path, "load", name="empty")
    assert isinstance(result, ToolError)
    assert "empty" in result


def test_load_already_active_returns_one_line(tmp_path):
    _write_skill(tmp_path, "alpha")
    block = _run(tmp_path, "load", name="alpha")
    history = [{"role": "tool", "content": str(block)}]
    assert _run(tmp_path, "load", messages=history, name="alpha") == "Skill 'alpha' is already active."


def test_two_skills_can_be_active(tmp_path):
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "beta")
    history = [{"role": "tool", "content": str(_run(tmp_path, "load", name="alpha"))}]
    history.append({"role": "tool", "content": str(_run(tmp_path, "load", messages=history, name="beta"))})
    assert [load.name for load in active_skills(history)] == ["alpha", "beta"]


def test_read_returns_resource(tmp_path):
    _write_skill(tmp_path, "alpha", files={"ref/a.md": "Resource A"})
    assert _run(tmp_path, "read", name="alpha", path="ref/a.md") == "Resource A"


def test_read_escape_is_a_security_error(tmp_path):
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "read", name="alpha", path="../../../secret.md")
    assert isinstance(result, ToolError)
    assert result.category == "security"


def test_read_skill_md_is_refused(tmp_path):
    _write_skill(tmp_path, "alpha")
    result = _run(tmp_path, "read", name="alpha", path="SKILL.md")
    assert isinstance(result, ToolError)
    assert "use skill(action=\"load\"" in result


def test_read_works_for_an_active_but_disabled_skill(tmp_path):
    _write_skill(tmp_path, "alpha", files={"a.md": "A"})
    history = [{"role": "user", "content": str(_run(tmp_path, "load", name="alpha"))}]
    result = _run(tmp_path, "read", messages=history, enabled=frozenset(), name="alpha", path="a.md")
    assert result == "A"


def test_unload_by_name_and_all(tmp_path):
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "beta")
    history = [
        {"role": "tool", "content": str(_run(tmp_path, "load", name="alpha"))},
        {"role": "tool", "content": str(_run(tmp_path, "load", name="beta"))},
    ]
    one = _run(tmp_path, "unload", messages=history, name="alpha")
    assert one.startswith("### SKILL UNLOADED: alpha\n")
    assert [load.name for load in active_skills(history + [{"role": "tool", "content": str(one)}])] == ["beta"]

    every = _run(tmp_path, "unload", messages=history)
    assert active_skills(history + [{"role": "tool", "content": str(every)}]) == []


def test_unload_without_active_skill_is_a_noop(tmp_path):
    assert _run(tmp_path, "unload") == "No active skill to unload."
    assert _run(tmp_path, "unload", name="alpha") == "Skill 'alpha' is not active."


def test_unknown_action(tmp_path):
    result = _run(tmp_path, "explode")
    assert isinstance(result, ToolError)
    assert "list, load, read, unload" in result


def test_load_with_app_updates_status_and_generation(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = MagicMock()
    app.messages = []
    skill(_ctx(tmp_path), "load", name="alpha", app=app)
    app._agent_registry.new_generation.assert_called_once()
    app.query_one.return_value.set_skill.assert_called_with("alpha")


def test_discover_skills_is_unfiltered(tmp_path):
    _write_skill(tmp_path, "alpha")
    assert [info.name for info in discover_skills(_ctx(tmp_path))] == ["alpha"]


def test_load_strips_the_name(tmp_path):
    _write_skill(tmp_path, "alpha")
    assert _run(tmp_path, "load", name=" alpha ").startswith("### SKILL LOADED: alpha\n")
