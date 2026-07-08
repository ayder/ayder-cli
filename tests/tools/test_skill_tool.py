from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.skill import (
    discover_skills,
    extract_skill_resource_refs,
    format_skill_bundle,
    load_skill_bundle,
    skill,
)
from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME


def _ctx(tmp_path):
    return ProjectContext(str(tmp_path))


def _write_skill(tmp_path, name: str, content: str = "## Domain\nPython") -> None:
    skill_dir = tmp_path / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _app():
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app.messages = [{"role": "system", "content": "base"}]
    app._active_skill = None
    app._agent_registry = None
    app.query_one = MagicMock(return_value=MagicMock())
    return app


def test_skill_tool_registered():
    assert "skill" in TOOL_DEFINITIONS_BY_NAME


def test_schema_action_enum():
    schema = TOOL_DEFINITIONS_BY_NAME["skill"].parameters
    assert schema["properties"]["action"]["enum"] == ["list", "load", "unload"]
    assert schema["required"] == ["action"]


def test_discover_skills_lists_only_dirs_with_skill_md(tmp_path):
    _write_skill(tmp_path, "alpha")
    (tmp_path / ".ayder" / "skills" / "missing").mkdir()
    (tmp_path / ".ayder" / "skills" / "file").write_text("", encoding="utf-8")

    assert [info.name for info in discover_skills(_ctx(tmp_path))] == ["alpha"]


def test_list_no_skills(tmp_path):
    result = skill(_ctx(tmp_path), "list")
    assert isinstance(result, ToolSuccess)
    assert result == "No skills found in .ayder/skills/"


def test_load_requires_name(tmp_path):
    result = skill(_ctx(tmp_path), "load", app=_app())
    assert isinstance(result, ToolError)
    assert "required" in result


def test_load_unknown_skill_reports_available(tmp_path):
    _write_skill(tmp_path, "alpha")

    result = load_skill_bundle(_ctx(tmp_path), "missing")

    assert isinstance(result, ToolError)
    assert "Unknown skill: 'missing'" in result
    assert "Available: alpha" in result


def test_load_empty_skill_returns_error(tmp_path):
    _write_skill(tmp_path, "empty", "")

    result = load_skill_bundle(_ctx(tmp_path), "empty")

    assert isinstance(result, ToolError)
    assert "empty" in result


def test_load_reads_skill_md(tmp_path):
    _write_skill(tmp_path, "alpha", "Skill body")

    result = load_skill_bundle(_ctx(tmp_path), "alpha")

    assert not isinstance(result, ToolError)
    assert result.skill_content == "Skill body"


def test_load_reads_markdown_linked_reference(tmp_path):
    _write_skill(tmp_path, "alpha", "Read [rules](references/rules.md).")
    ref = tmp_path / ".ayder" / "skills" / "alpha" / "references" / "rules.md"
    ref.parent.mkdir()
    ref.write_text("Rule content", encoding="utf-8")

    result = load_skill_bundle(_ctx(tmp_path), "alpha")

    assert not isinstance(result, ToolError)
    assert [resource.content for resource in result.resources] == ["Rule content"]


def test_load_reads_backticked_reference_path(tmp_path):
    _write_skill(tmp_path, "alpha", "Read `references/rules.md`.")
    ref = tmp_path / ".ayder" / "skills" / "alpha" / "references" / "rules.md"
    ref.parent.mkdir()
    ref.write_text("Rule content", encoding="utf-8")

    result = load_skill_bundle(_ctx(tmp_path), "alpha")

    assert not isinstance(result, ToolError)
    assert [resource.content for resource in result.resources] == ["Rule content"]


def test_load_deduplicates_references(tmp_path):
    _write_skill(
        tmp_path,
        "alpha",
        "Read [rules](references/rules.md) and `references/rules.md`.",
    )
    ref = tmp_path / ".ayder" / "skills" / "alpha" / "references" / "rules.md"
    ref.parent.mkdir()
    ref.write_text("Rule content", encoding="utf-8")

    result = load_skill_bundle(_ctx(tmp_path), "alpha")

    assert not isinstance(result, ToolError)
    assert len(result.resources) == 1


def test_load_rejects_parent_traversal_reference(tmp_path):
    _write_skill(tmp_path, "alpha", "Read [outside](../outside.md).")
    outside = tmp_path / ".ayder" / "skills" / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    skill_path = tmp_path / ".ayder" / "skills" / "alpha" / "SKILL.md"

    assert extract_skill_resource_refs(skill_path, skill_path.read_text()) == []


def test_load_ignores_absolute_paths_and_urls(tmp_path):
    _write_skill(
        tmp_path,
        "alpha",
        "Read [abs](/tmp/nope.md), [web](https://example.com/a.md), and `#anchor`.",
    )
    skill_path = tmp_path / ".ayder" / "skills" / "alpha" / "SKILL.md"

    assert extract_skill_resource_refs(skill_path, skill_path.read_text()) == []


def test_load_with_app_injects_one_active_skill(tmp_path):
    _write_skill(tmp_path, "alpha", "Skill body")
    app = _app()

    result = skill(_ctx(tmp_path), "load", name="alpha", app=app)

    assert isinstance(result, ToolSuccess)
    active = [msg for msg in app.messages if msg["content"].startswith("### ACTIVE SKILL:")]
    assert len(active) == 1
    assert "Skill body" in active[0]["content"]


def test_loading_second_skill_replaces_first(tmp_path):
    _write_skill(tmp_path, "alpha", "Alpha body")
    _write_skill(tmp_path, "beta", "Beta body")
    app = _app()

    skill(_ctx(tmp_path), "load", name="alpha", app=app)
    skill(_ctx(tmp_path), "load", name="beta", app=app)

    active = [msg for msg in app.messages if msg["content"].startswith("### ACTIVE SKILL:")]
    assert len(active) == 1
    assert "Beta body" in active[0]["content"]
    assert app._active_skill == "beta"


def test_unload_removes_active_skill(tmp_path):
    _write_skill(tmp_path, "alpha", "Skill body")
    app = _app()
    skill(_ctx(tmp_path), "load", name="alpha", app=app)

    result = skill(_ctx(tmp_path), "unload", app=app)

    assert isinstance(result, ToolSuccess)
    assert app._active_skill is None
    assert all(not msg["content"].startswith("### ACTIVE SKILL:") for msg in app.messages)


def test_unload_without_active_skill_is_successful_noop(tmp_path):
    app = _app()

    result = skill(_ctx(tmp_path), "unload", app=app)

    assert isinstance(result, ToolSuccess)
    assert result == "No active skill to unload."


def test_load_without_app_returns_unsupported_error(tmp_path):
    _write_skill(tmp_path, "alpha", "Skill body")

    result = skill(_ctx(tmp_path), "load", name="alpha")

    assert isinstance(result, ToolError)
    assert result.category == "unsupported"


def test_format_skill_bundle_includes_reference_headers(tmp_path):
    _write_skill(tmp_path, "alpha", "Read [rules](references/rules.md).")
    ref = tmp_path / ".ayder" / "skills" / "alpha" / "references" / "rules.md"
    ref.parent.mkdir()
    ref.write_text("Rule content", encoding="utf-8")
    bundle = load_skill_bundle(_ctx(tmp_path), "alpha")

    assert not isinstance(bundle, ToolError)
    formatted = format_skill_bundle(bundle)
    assert "### Referenced File: references/rules.md" in formatted
    assert "Rule content" in formatted
